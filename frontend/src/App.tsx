import { useEffect, useState, useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

interface ModelSupport {
  model_id: string;
  release_date: string;
  sdk_support_timestamp: string | null;
  frontend_support_timestamp: string | null;
  index_results_timestamp: string | null;
  infra_litellm_timestamp: string | null;
  litellm_support_timestamp: string | null;
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function getDaysDiff(dateStr: string | null, releaseDate: string): string {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  const release = new Date(releaseDate);
  const diffTime = date.getTime() - release.getTime();
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
  if (diffDays < 0) return `${Math.abs(diffDays)}d before`;
  if (diffDays === 0) return 'Same day';
  return `+${diffDays}d`;
}

function StatusBadge({ timestamp }: { timestamp: string | null }) {
  if (timestamp) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-900/50 text-green-400 border border-green-700">
        ✓ Supported
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-800 text-gray-400 border border-gray-700">
      — Not found
    </span>
  );
}

function App() {
  const [models, setModels] = useState<ModelSupport[]>([]);
  const [sortField, setSortField] = useState<keyof ModelSupport>('model_id');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/all_models.json')
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load data');
        return res.json();
      })
      .then((data) => {
        setModels(data as ModelSupport[]);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  const sortedModels = [...models].sort((a, b) => {
    const aVal = a[sortField];
    const bVal = b[sortField];
    if (aVal === null && bVal === null) return 0;
    if (aVal === null) return 1;
    if (bVal === null) return -1;
    if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
    return 0;
  });

  const handleSort = (field: keyof ModelSupport) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  // Compute rolling average data for charts
  const chartData = useMemo(() => {
    if (models.length === 0) return [];

    // Sort models by release date
    const sortedByRelease = [...models].sort(
      (a, b) => new Date(a.release_date).getTime() - new Date(b.release_date).getTime()
    );

    // Get date range
    const minDate = new Date(sortedByRelease[0].release_date);
    const maxDate = new Date();
    
    const data: Array<{
      date: string;
      sdkPercent: number;
      frontendPercent: number;
      litellmPercent: number;
      infraPercent: number;
      indexPercent: number;
      sdkAvgDays: number | null;
      frontendAvgDays: number | null;
      litellmAvgDays: number | null;
      infraAvgDays: number | null;
      indexAvgDays: number | null;
    }> = [];

    // Generate data points for each month
    const currentDate = new Date(minDate);
    while (currentDate <= maxDate) {
      const windowEnd = new Date(currentDate);
      const windowStart = new Date(currentDate);
      windowStart.setDate(windowStart.getDate() - 60);

      // Get models released within the 60-day window before this date
      const modelsInWindow = sortedByRelease.filter((m) => {
        const releaseDate = new Date(m.release_date);
        return releaseDate >= windowStart && releaseDate <= windowEnd;
      });

      if (modelsInWindow.length > 0) {
        // Calculate support percentages
        const sdkSupported = modelsInWindow.filter((m) => m.sdk_support_timestamp).length;
        const frontendSupported = modelsInWindow.filter((m) => m.frontend_support_timestamp).length;
        const litellmSupported = modelsInWindow.filter((m) => m.litellm_support_timestamp).length;
        const infraSupported = modelsInWindow.filter((m) => m.infra_litellm_timestamp).length;
        const indexSupported = modelsInWindow.filter((m) => m.index_results_timestamp).length;

        // Calculate average support time (days from release to support)
        const calcAvgDays = (
          models: ModelSupport[],
          timestampField: keyof ModelSupport
        ): number | null => {
          const supported = models.filter((m) => m[timestampField]);
          if (supported.length === 0) return null;
          const totalDays = supported.reduce((sum, m) => {
            const releaseDate = new Date(m.release_date);
            const supportDate = new Date(m[timestampField] as string);
            return sum + Math.max(0, (supportDate.getTime() - releaseDate.getTime()) / (1000 * 60 * 60 * 24));
          }, 0);
          return Math.round(totalDays / supported.length);
        };

        data.push({
          date: currentDate.toISOString().split('T')[0],
          sdkPercent: Math.round((sdkSupported / modelsInWindow.length) * 100),
          frontendPercent: Math.round((frontendSupported / modelsInWindow.length) * 100),
          litellmPercent: Math.round((litellmSupported / modelsInWindow.length) * 100),
          infraPercent: Math.round((infraSupported / modelsInWindow.length) * 100),
          indexPercent: Math.round((indexSupported / modelsInWindow.length) * 100),
          sdkAvgDays: calcAvgDays(modelsInWindow, 'sdk_support_timestamp'),
          frontendAvgDays: calcAvgDays(modelsInWindow, 'frontend_support_timestamp'),
          litellmAvgDays: calcAvgDays(modelsInWindow, 'litellm_support_timestamp'),
          infraAvgDays: calcAvgDays(modelsInWindow, 'infra_litellm_timestamp'),
          indexAvgDays: calcAvgDays(modelsInWindow, 'index_results_timestamp'),
        });
      }

      // Move to next week
      currentDate.setDate(currentDate.getDate() + 7);
    }

    return data;
  }, [models]);

  const SortIcon = ({ field }: { field: keyof ModelSupport }) => {
    if (sortField !== field) return <span className="text-gray-600 ml-1">↕</span>;
    return <span className="text-blue-400 ml-1">{sortDirection === 'asc' ? '↑' : '↓'}</span>;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0c0e10] text-gray-100 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-400 mx-auto"></div>
          <p className="mt-4 text-[#9099ac]">Loading model data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#0c0e10] text-gray-100 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400">Error: {error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0c0e10] text-gray-100">
      <header className="border-b border-[#3c3c4a] bg-[#1f2228]">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <h1 className="text-2xl font-bold text-white">OpenHands LLM Support Tracker</h1>
          <p className="text-[#9099ac] mt-1">
            Track when language models are supported across the OpenHands ecosystem
          </p>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8">
        <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-[#24272e] border-b border-[#3c3c4a]">
                  <th
                    className="px-4 py-3 text-left text-sm font-semibold text-[#c4cbda] cursor-pointer hover:bg-[#31343d]"
                    onClick={() => handleSort('model_id')}
                  >
                    Model <SortIcon field="model_id" />
                  </th>
                  <th
                    className="px-4 py-3 text-left text-sm font-semibold text-[#c4cbda] cursor-pointer hover:bg-[#31343d]"
                    onClick={() => handleSort('release_date')}
                  >
                    Release Date <SortIcon field="release_date" />
                  </th>
                  <th
                    className="px-4 py-3 text-left text-sm font-semibold text-[#c4cbda] cursor-pointer hover:bg-[#31343d]"
                    onClick={() => handleSort('sdk_support_timestamp')}
                  >
                    SDK Support <SortIcon field="sdk_support_timestamp" />
                  </th>
                  <th
                    className="px-4 py-3 text-left text-sm font-semibold text-[#c4cbda] cursor-pointer hover:bg-[#31343d]"
                    onClick={() => handleSort('frontend_support_timestamp')}
                  >
                    Frontend <SortIcon field="frontend_support_timestamp" />
                  </th>
                  <th
                    className="px-4 py-3 text-left text-sm font-semibold text-[#c4cbda] cursor-pointer hover:bg-[#31343d]"
                    onClick={() => handleSort('litellm_support_timestamp')}
                  >
                    LiteLLM <SortIcon field="litellm_support_timestamp" />
                  </th>
                  <th
                    className="px-4 py-3 text-left text-sm font-semibold text-[#c4cbda] cursor-pointer hover:bg-[#31343d]"
                    onClick={() => handleSort('infra_litellm_timestamp')}
                  >
                    Infra Proxy <SortIcon field="infra_litellm_timestamp" />
                  </th>
                  <th
                    className="px-4 py-3 text-left text-sm font-semibold text-[#c4cbda] cursor-pointer hover:bg-[#31343d]"
                    onClick={() => handleSort('index_results_timestamp')}
                  >
                    Index Results <SortIcon field="index_results_timestamp" />
                  </th>
                </tr>
              </thead>
              <tbody>
                {sortedModels.map((model, index) => (
                  <tr
                    key={model.model_id}
                    className={`border-b border-[#3c3c4a] hover:bg-[#24272e] ${
                      index % 2 === 0 ? 'bg-[#1f2228]' : 'bg-[#1a1d22]'
                    }`}
                  >
                    <td className="px-4 py-3">
                      <span className="font-medium text-white">{model.model_id}</span>
                    </td>
                    <td className="px-4 py-3 text-[#9099ac]">
                      {formatDate(model.release_date)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-1">
                        <StatusBadge timestamp={model.sdk_support_timestamp} />
                        {model.sdk_support_timestamp && (
                          <span className="text-xs text-[#9099ac]">
                            {formatDate(model.sdk_support_timestamp)}
                            <span className="ml-1 text-blue-400">
                              ({getDaysDiff(model.sdk_support_timestamp, model.release_date)})
                            </span>
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-1">
                        <StatusBadge timestamp={model.frontend_support_timestamp} />
                        {model.frontend_support_timestamp && (
                          <span className="text-xs text-[#9099ac]">
                            {formatDate(model.frontend_support_timestamp)}
                            <span className="ml-1 text-blue-400">
                              ({getDaysDiff(model.frontend_support_timestamp, model.release_date)})
                            </span>
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-1">
                        <StatusBadge timestamp={model.litellm_support_timestamp} />
                        {model.litellm_support_timestamp && (
                          <span className="text-xs text-[#9099ac]">
                            {formatDate(model.litellm_support_timestamp)}
                            <span className="ml-1 text-blue-400">
                              ({getDaysDiff(model.litellm_support_timestamp, model.release_date)})
                            </span>
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-1">
                        <StatusBadge timestamp={model.infra_litellm_timestamp} />
                        {model.infra_litellm_timestamp && (
                          <span className="text-xs text-[#9099ac]">
                            {formatDate(model.infra_litellm_timestamp)}
                            <span className="ml-1 text-blue-400">
                              ({getDaysDiff(model.infra_litellm_timestamp, model.release_date)})
                            </span>
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-1">
                        <StatusBadge timestamp={model.index_results_timestamp} />
                        {model.index_results_timestamp && (
                          <span className="text-xs text-[#9099ac]">
                            {formatDate(model.index_results_timestamp)}
                            <span className="ml-1 text-blue-400">
                              ({getDaysDiff(model.index_results_timestamp, model.release_date)})
                            </span>
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="mt-8 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-4">
            <h3 className="text-sm font-medium text-[#9099ac]">Total Models</h3>
            <p className="text-2xl font-bold text-white mt-1">{models.length}</p>
          </div>
          <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-4">
            <h3 className="text-sm font-medium text-[#9099ac]">SDK Supported</h3>
            <p className="text-2xl font-bold text-green-400 mt-1">
              {models.filter((m) => m.sdk_support_timestamp).length}
            </p>
          </div>
          <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-4">
            <h3 className="text-sm font-medium text-[#9099ac]">Frontend</h3>
            <p className="text-2xl font-bold text-green-400 mt-1">
              {models.filter((m) => m.frontend_support_timestamp).length}
            </p>
          </div>
          <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-4">
            <h3 className="text-sm font-medium text-[#9099ac]">LiteLLM</h3>
            <p className="text-2xl font-bold text-green-400 mt-1">
              {models.filter((m) => m.litellm_support_timestamp).length}
            </p>
          </div>
          <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-4">
            <h3 className="text-sm font-medium text-[#9099ac]">Infra Proxy</h3>
            <p className="text-2xl font-bold text-green-400 mt-1">
              {models.filter((m) => m.infra_litellm_timestamp).length}
            </p>
          </div>
          <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-4">
            <h3 className="text-sm font-medium text-[#9099ac]">Index Results</h3>
            <p className="text-2xl font-bold text-green-400 mt-1">
              {models.filter((m) => m.index_results_timestamp).length}
            </p>
          </div>
        </div>

        {/* Charts Section */}
        {chartData.length > 0 && (
          <div className="mt-8 grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Support Percentage Chart */}
            <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-6">
              <h3 className="text-lg font-semibold text-white mb-4">
                Support Percentage (60-day Rolling Average)
              </h3>
              <p className="text-sm text-[#9099ac] mb-4">
                Percentage of models released in the past 60 days that have support
              </p>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#3c3c4a" />
                  <XAxis
                    dataKey="date"
                    stroke="#9099ac"
                    tick={{ fill: '#9099ac', fontSize: 12 }}
                    tickFormatter={(value) => {
                      const date = new Date(value);
                      return `${date.getMonth() + 1}/${date.getDate()}`;
                    }}
                  />
                  <YAxis
                    stroke="#9099ac"
                    tick={{ fill: '#9099ac', fontSize: 12 }}
                    domain={[0, 100]}
                    tickFormatter={(value) => `${value}%`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1f2228',
                      border: '1px solid #3c3c4a',
                      borderRadius: '8px',
                    }}
                    labelStyle={{ color: '#fff' }}
                    formatter={(value) => [`${value}%`, '']}
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="sdkPercent"
                    name="SDK"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="frontendPercent"
                    name="Frontend"
                    stroke="#22c55e"
                    strokeWidth={2}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="litellmPercent"
                    name="LiteLLM"
                    stroke="#f59e0b"
                    strokeWidth={2}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="infraPercent"
                    name="Infra"
                    stroke="#ec4899"
                    strokeWidth={2}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="indexPercent"
                    name="Index"
                    stroke="#8b5cf6"
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Average Support Time Chart */}
            <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-6">
              <h3 className="text-lg font-semibold text-white mb-4">
                Average Support Time (60-day Rolling Average)
              </h3>
              <p className="text-sm text-[#9099ac] mb-4">
                Average days from model release to support for models released in the past 60 days
              </p>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#3c3c4a" />
                  <XAxis
                    dataKey="date"
                    stroke="#9099ac"
                    tick={{ fill: '#9099ac', fontSize: 12 }}
                    tickFormatter={(value) => {
                      const date = new Date(value);
                      return `${date.getMonth() + 1}/${date.getDate()}`;
                    }}
                  />
                  <YAxis
                    stroke="#9099ac"
                    tick={{ fill: '#9099ac', fontSize: 12 }}
                    tickFormatter={(value) => `${value}d`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1f2228',
                      border: '1px solid #3c3c4a',
                      borderRadius: '8px',
                    }}
                    labelStyle={{ color: '#fff' }}
                    formatter={(value) =>
                      value !== null ? [`${value} days`, ''] : ['N/A', '']
                    }
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="sdkAvgDays"
                    name="SDK"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="frontendAvgDays"
                    name="Frontend"
                    stroke="#22c55e"
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="litellmAvgDays"
                    name="LiteLLM"
                    stroke="#f59e0b"
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="infraAvgDays"
                    name="Infra"
                    stroke="#ec4899"
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="indexAvgDays"
                    name="Index"
                    stroke="#8b5cf6"
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        <footer className="mt-8 text-center text-[#9099ac] text-sm">
          <p>
            Data sourced from{' '}
            <a
              href="https://github.com/OpenHands/software-agent-sdk"
              className="text-blue-400 hover:underline"
            >
              software-agent-sdk
            </a>
            ,{' '}
            <a
              href="https://github.com/OpenHands/OpenHands"
              className="text-blue-400 hover:underline"
            >
              OpenHands
            </a>
            ,{' '}
            <a
              href="https://github.com/OpenHands/openhands-index-results"
              className="text-blue-400 hover:underline"
            >
              openhands-index-results
            </a>
            , and{' '}
            <a
              href="https://github.com/All-Hands-AI/infra"
              className="text-blue-400 hover:underline"
            >
              All-Hands-AI/infra
            </a>
          </p>
        </footer>
      </main>
    </div>
  );
}

export default App;

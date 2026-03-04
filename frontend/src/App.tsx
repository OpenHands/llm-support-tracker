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
  tier: number;
  sdk_support_timestamp: string | null;
  frontend_support_timestamp: string | null;
  index_results_timestamp: string | null;
  eval_proxy_timestamp: string | null;
  prod_proxy_timestamp: string | null;
  litellm_support_timestamp: string | null;
}

type Aspect = 'litellm' | 'eval_proxy' | 'prod_proxy' | 'sdk' | 'frontend' | 'index' | 'complete';

const ASPECT_FIELDS: Record<Exclude<Aspect, 'complete'>, keyof ModelSupport> = {
  litellm: 'litellm_support_timestamp',
  eval_proxy: 'eval_proxy_timestamp',
  prod_proxy: 'prod_proxy_timestamp',
  sdk: 'sdk_support_timestamp',
  frontend: 'frontend_support_timestamp',
  index: 'index_results_timestamp',
};

const MODEL_FAMILIES: Record<string, RegExp> = {
  claude: /claude/i,
  gpt: /gpt/i,
  gemini: /gemini/i,
  open: /qwen|minimax|glm|kimi/i,
};

interface DaysUnsupportedDataPoint {
  date: string;
  litellm: number;
  eval_proxy: number;
  prod_proxy: number;
  sdk: number;
  frontend: number;
  index: number;
  complete: number;
}

export function isModelSupportedForAspect(
  model: ModelSupport,
  aspect: Aspect,
  asOfDate: Date
): boolean {
  if (aspect === 'complete') {
    return (Object.keys(ASPECT_FIELDS) as Exclude<Aspect, 'complete'>[]).every((a) =>
      isModelSupportedForAspect(model, a, asOfDate)
    );
  }

  const field = ASPECT_FIELDS[aspect];
  const supportTimestamp = model[field] as string | null;
  if (!supportTimestamp) return false;

  const supportDate = new Date(supportTimestamp);
  return supportDate <= asOfDate;
}

export function computeDaysUnsupported(
  models: ModelSupport[],
  modelPattern: RegExp,
  aspect: Aspect
): Array<{ date: string; daysUnsupported: number }> {
  const matchingModels = models.filter((m) => modelPattern.test(m.model_id));
  if (matchingModels.length === 0) return [];

  const sortedByRelease = [...matchingModels].sort(
    (a, b) => new Date(a.release_date).getTime() - new Date(b.release_date).getTime()
  );

  const minDate = new Date(sortedByRelease[0].release_date);
  const maxDate = new Date();

  const result: Array<{ date: string; daysUnsupported: number }> = [];
  let daysUnsupported = 0;

  const currentDate = new Date(minDate);
  while (currentDate <= maxDate) {
    const releasedModels = matchingModels.filter((m) => {
      const releaseDate = new Date(m.release_date);
      return releaseDate <= currentDate;
    });

    if (releasedModels.length > 0) {
      const anyUnsupported = releasedModels.some(
        (m) => !isModelSupportedForAspect(m, aspect, currentDate)
      );

      if (anyUnsupported) {
        daysUnsupported++;
      } else {
        daysUnsupported = 0;
      }

      result.push({
        date: currentDate.toISOString().split('T')[0],
        daysUnsupported,
      });
    }

    currentDate.setDate(currentDate.getDate() + 1);
  }

  return result;
}

export function applyRollingAverage(
  data: Map<string, number>,
  sortedDates: string[],
  windowDays: number = 30
): Map<string, number> {
  const result = new Map<string, number>();

  for (let i = 0; i < sortedDates.length; i++) {
    const currentDate = new Date(sortedDates[i]);
    let sum = 0;
    let count = 0;

    // Look back windowDays days
    for (let j = i; j >= 0; j--) {
      const pastDate = new Date(sortedDates[j]);
      const diffDays = (currentDate.getTime() - pastDate.getTime()) / (1000 * 60 * 60 * 24);
      if (diffDays > windowDays) break;

      const value = data.get(sortedDates[j]);
      if (value !== undefined) {
        sum += value;
        count++;
      }
    }

    result.set(sortedDates[i], count > 0 ? Math.round(sum / count) : 0);
  }

  return result;
}

// Generate consistent weekly sample dates (every Sunday) within a date range
export function getWeeklySampleDates(startDate: string, endDate: string): string[] {
  const start = new Date(startDate);
  const end = new Date(endDate);
  const result: string[] = [];

  // Find the first Sunday on or after start
  const current = new Date(start);
  const dayOfWeek = current.getDay();
  if (dayOfWeek !== 0) {
    current.setDate(current.getDate() + (7 - dayOfWeek));
  }

  while (current <= end) {
    result.push(current.toISOString().split('T')[0]);
    current.setDate(current.getDate() + 7);
  }

  // Always include the end date if it's not already included
  const endStr = end.toISOString().split('T')[0];
  if (result.length === 0 || result[result.length - 1] !== endStr) {
    result.push(endStr);
  }

  return result;
}

export function computeFamilyChartData(
  models: ModelSupport[],
  modelPattern: RegExp,
  sampleDates?: string[],
  useSmoothing: boolean = true
): DaysUnsupportedDataPoint[] {
  const aspects: Aspect[] = ['litellm', 'eval_proxy', 'prod_proxy', 'sdk', 'frontend', 'index', 'complete'];

  const rawAspectData: Record<Aspect, Map<string, number>> = {} as Record<Aspect, Map<string, number>>;
  for (const aspect of aspects) {
    const data = computeDaysUnsupported(models, modelPattern, aspect);
    rawAspectData[aspect] = new Map(data.map((d) => [d.date, d.daysUnsupported]));
  }

  const allDates = new Set<string>();
  for (const aspect of aspects) {
    for (const date of rawAspectData[aspect].keys()) {
      allDates.add(date);
    }
  }

  const sortedDates = Array.from(allDates).sort();
  if (sortedDates.length === 0) return [];

  // Apply 30-day rolling average to smooth the data (if enabled)
  const aspectDataToUse: Record<Aspect, Map<string, number>> = useSmoothing
    ? {} as Record<Aspect, Map<string, number>>
    : rawAspectData;
  
  if (useSmoothing) {
    for (const aspect of aspects) {
      aspectDataToUse[aspect] = applyRollingAverage(rawAspectData[aspect], sortedDates, 30);
    }
  }

  // Use provided sample dates or generate weekly dates
  const weeklyDates = sampleDates ?? getWeeklySampleDates(sortedDates[0], sortedDates[sortedDates.length - 1]);

  // Filter to dates that exist in our data range
  const validDates = weeklyDates.filter((date) => date >= sortedDates[0] && date <= sortedDates[sortedDates.length - 1]);

  return validDates.map((date) => {
    // For dates that don't have exact data, find the closest previous date
    const getValueForDate = (aspectData: Map<string, number>, targetDate: string): number => {
      if (aspectData.has(targetDate)) {
        return aspectData.get(targetDate)!;
      }
      // Find closest previous date
      for (let i = sortedDates.length - 1; i >= 0; i--) {
        if (sortedDates[i] <= targetDate && aspectData.has(sortedDates[i])) {
          return aspectData.get(sortedDates[i])!;
        }
      }
      return 0;
    };

    return {
      date,
      litellm: getValueForDate(aspectDataToUse.litellm, date),
      eval_proxy: getValueForDate(aspectDataToUse.eval_proxy, date),
      prod_proxy: getValueForDate(aspectDataToUse.prod_proxy, date),
      sdk: getValueForDate(aspectDataToUse.sdk, date),
      frontend: getValueForDate(aspectDataToUse.frontend, date),
      index: getValueForDate(aspectDataToUse.index, date),
      complete: getValueForDate(aspectDataToUse.complete, date),
    };
  });
}

interface AverageDataPoint {
  date: string;
  litellm: number;
  eval_proxy: number;
  prod_proxy: number;
  sdk: number;
  frontend: number;
  index: number;
  complete: number;
}

export function computeAverageChartData(
  familyData: Record<string, DaysUnsupportedDataPoint[]>
): AverageDataPoint[] {
  const families = Object.keys(familyData);
  if (families.length === 0) return [];

  // All families should now share the same dates since we use consistent sampling
  // Build a map from date -> family -> data for quick lookups
  const familyMaps: Record<string, Map<string, DaysUnsupportedDataPoint>> = {};
  for (const family of families) {
    familyMaps[family] = new Map(familyData[family].map((p) => [p.date, p]));
  }

  // Find the date range where ALL families have data
  const familyDateRanges = families.map((family) => {
    const dates = familyData[family].map((p) => p.date).sort();
    return { start: dates[0], end: dates[dates.length - 1] };
  });

  const latestStart = familyDateRanges.reduce(
    (max, range) => (range.start > max ? range.start : max),
    familyDateRanges[0].start
  );
  const earliestEnd = familyDateRanges.reduce(
    (min, range) => (range.end < min ? range.end : min),
    familyDateRanges[0].end
  );

  // Get all unique dates within the common range
  const allDates = new Set<string>();
  for (const family of families) {
    for (const point of familyData[family]) {
      if (point.date >= latestStart && point.date <= earliestEnd) {
        allDates.add(point.date);
      }
    }
  }

  const sortedDates = Array.from(allDates).sort();

  return sortedDates.map((date) => {
    const aspects: (keyof Omit<DaysUnsupportedDataPoint, 'date'>)[] = [
      'litellm', 'eval_proxy', 'prod_proxy', 'sdk', 'frontend', 'index', 'complete'
    ];

    const result: AverageDataPoint = { date, litellm: 0, eval_proxy: 0, prod_proxy: 0, sdk: 0, frontend: 0, index: 0, complete: 0 };

    for (const aspect of aspects) {
      let sum = 0;
      let count = 0;
      for (const family of families) {
        const point = familyMaps[family].get(date);
        if (point) {
          sum += point[aspect];
          count++;
        }
      }
      result[aspect] = count > 0 ? Math.round(sum / count) : 0;
    }

    return result;
  });
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
  const [showTier2, setShowTier2] = useState(false);
  const [useSmoothing, setUseSmoothing] = useState(true);

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

  // Filter models by tier, then sort
  const filteredModels = showTier2 ? models : models.filter((m) => m.tier === 1);
  const sortedModels = [...filteredModels].sort((a, b) => {
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

  // Compute days unsupported data for model family charts (tier 1 models only)
  const daysUnsupportedData = useMemo(() => {
    // Filter to tier 1 models only for metrics
    const tier1Models = models.filter((m) => m.tier === 1);
    if (tier1Models.length === 0) return { claude: [], gpt: [], gemini: [], open: [], average: [] };

    // First, determine the global date range across all families for consistent sampling
    const allReleaseDates = tier1Models.map((m) => m.release_date).sort();
    const globalStart = allReleaseDates[0];
    const globalEnd = new Date().toISOString().split('T')[0];
    const sharedSampleDates = getWeeklySampleDates(globalStart, globalEnd);

    const familyData: Record<string, DaysUnsupportedDataPoint[]> = {};
    for (const [familyName, pattern] of Object.entries(MODEL_FAMILIES)) {
      familyData[familyName] = computeFamilyChartData(tier1Models, pattern, sharedSampleDates, useSmoothing);
    }

    const averageData = computeAverageChartData(familyData);

    return {
      claude: familyData.claude,
      gpt: familyData.gpt,
      gemini: familyData.gemini,
      open: familyData.open,
      average: averageData,
    };
  }, [models, useSmoothing]);

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
          <div className="px-4 py-3 border-b border-[#3c3c4a] flex items-center justify-between">
            <span className="text-sm text-[#9099ac]">
              Showing {sortedModels.length} of {models.length} models
            </span>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={showTier2}
                onChange={(e) => setShowTier2(e.target.checked)}
                className="w-4 h-4 rounded border-[#3c3c4a] bg-[#24272e] text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
              />
              <span className="text-sm text-[#9099ac]">Show tier 2 models</span>
            </label>
          </div>
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
                    onClick={() => handleSort('litellm_support_timestamp')}
                  >
                    LiteLLM <SortIcon field="litellm_support_timestamp" />
                  </th>
                  <th
                    className="px-4 py-3 text-left text-sm font-semibold text-[#c4cbda] cursor-pointer hover:bg-[#31343d]"
                    onClick={() => handleSort('eval_proxy_timestamp')}
                  >
                    Eval Proxy <SortIcon field="eval_proxy_timestamp" />
                  </th>
                  <th
                    className="px-4 py-3 text-left text-sm font-semibold text-[#c4cbda] cursor-pointer hover:bg-[#31343d]"
                    onClick={() => handleSort('prod_proxy_timestamp')}
                  >
                    Prod Proxy <SortIcon field="prod_proxy_timestamp" />
                  </th>
                  <th
                    className="px-4 py-3 text-left text-sm font-semibold text-[#c4cbda] cursor-pointer hover:bg-[#31343d]"
                    onClick={() => handleSort('sdk_support_timestamp')}
                  >
                    SDK <SortIcon field="sdk_support_timestamp" />
                  </th>
                  <th
                    className="px-4 py-3 text-left text-sm font-semibold text-[#c4cbda] cursor-pointer hover:bg-[#31343d]"
                    onClick={() => handleSort('frontend_support_timestamp')}
                  >
                    Frontend <SortIcon field="frontend_support_timestamp" />
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
                        <StatusBadge timestamp={model.eval_proxy_timestamp} />
                        {model.eval_proxy_timestamp && (
                          <span className="text-xs text-[#9099ac]">
                            {formatDate(model.eval_proxy_timestamp)}
                            <span className="ml-1 text-blue-400">
                              ({getDaysDiff(model.eval_proxy_timestamp, model.release_date)})
                            </span>
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-1">
                        <StatusBadge timestamp={model.prod_proxy_timestamp} />
                        {model.prod_proxy_timestamp && (
                          <span className="text-xs text-[#9099ac]">
                            {formatDate(model.prod_proxy_timestamp)}
                            <span className="ml-1 text-blue-400">
                              ({getDaysDiff(model.prod_proxy_timestamp, model.release_date)})
                            </span>
                          </span>
                        )}
                      </div>
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

        <div className="mt-8 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
          <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-4">
            <h3 className="text-sm font-medium text-[#9099ac]">Total Models</h3>
            <p className="text-2xl font-bold text-white mt-1">{models.length}</p>
          </div>
          <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-4">
            <h3 className="text-sm font-medium text-[#9099ac]">LiteLLM</h3>
            <p className="text-2xl font-bold text-green-400 mt-1">
              {models.filter((m) => m.litellm_support_timestamp).length}
            </p>
          </div>
          <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-4">
            <h3 className="text-sm font-medium text-[#9099ac]">Eval Proxy</h3>
            <p className="text-2xl font-bold text-green-400 mt-1">
              {models.filter((m) => m.eval_proxy_timestamp).length}
            </p>
          </div>
          <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-4">
            <h3 className="text-sm font-medium text-[#9099ac]">Prod Proxy</h3>
            <p className="text-2xl font-bold text-green-400 mt-1">
              {models.filter((m) => m.prod_proxy_timestamp).length}
            </p>
          </div>
          <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-4">
            <h3 className="text-sm font-medium text-[#9099ac]">SDK</h3>
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
            <h3 className="text-sm font-medium text-[#9099ac]">Index Results</h3>
            <p className="text-2xl font-bold text-green-400 mt-1">
              {models.filter((m) => m.index_results_timestamp).length}
            </p>
          </div>
        </div>

        {/* Days Unsupported Charts Section */}
        {(daysUnsupportedData.claude.length > 0 ||
          daysUnsupportedData.gpt.length > 0 ||
          daysUnsupportedData.gemini.length > 0 ||
          daysUnsupportedData.open.length > 0) && (
          <>
            <div className="mt-12 mb-6 flex items-center justify-between">
              <h2 className="text-xl font-bold text-white">
                Days Unsupported by Model Family
              </h2>
              <div className="flex items-center gap-3">
                <span className="text-sm text-[#9099ac]">Display:</span>
                <div className="flex bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-1">
                  <button
                    onClick={() => setUseSmoothing(false)}
                    className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                      !useSmoothing
                        ? 'bg-blue-600 text-white'
                        : 'text-[#9099ac] hover:text-white'
                    }`}
                  >
                    Raw Value
                  </button>
                  <button
                    onClick={() => setUseSmoothing(true)}
                    className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                      useSmoothing
                        ? 'bg-blue-600 text-white'
                        : 'text-[#9099ac] hover:text-white'
                    }`}
                  >
                    30-Day Average
                  </button>
                </div>
              </div>
            </div>
            <p className="text-sm text-[#9099ac] mb-6">
              Number of consecutive days where at least one model in the family has been unsupported.
              A value of 0 means all released models in the family are fully supported for that aspect.
            </p>
            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
              {/* Claude Chart */}
              {daysUnsupportedData.claude.length > 0 && (
                <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-6">
                  <h3 className="text-lg font-semibold text-white mb-4">Claude Models</h3>
                  <p className="text-xs text-[#9099ac] mb-4">Pattern: claude</p>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={daysUnsupportedData.claude}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#3c3c4a" />
                      <XAxis
                        dataKey="date"
                        stroke="#9099ac"
                        tick={{ fill: '#9099ac', fontSize: 10 }}
                        tickFormatter={(value) => {
                          const date = new Date(value);
                          return `${date.getMonth() + 1}/${date.getDate()}`;
                        }}
                      />
                      <YAxis
                        stroke="#9099ac"
                        tick={{ fill: '#9099ac', fontSize: 10 }}
                        tickFormatter={(value) => `${value}d`}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1f2228',
                          border: '1px solid #3c3c4a',
                          borderRadius: '8px',
                        }}
                        labelStyle={{ color: '#fff' }}
                        formatter={(value) => [`${value} days`, '']}
                      />
                      <Legend wrapperStyle={{ fontSize: '10px' }} />
                      <Line type="monotone" dataKey="litellm" name="LiteLLM" stroke="#f59e0b" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="eval_proxy" name="Eval Proxy" stroke="#ec4899" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="prod_proxy" name="Prod Proxy" stroke="#14b8a6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="sdk" name="SDK" stroke="#3b82f6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="frontend" name="Frontend" stroke="#22c55e" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="index" name="Index" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="complete" name="Complete" stroke="#ef4444" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* GPT Chart */}
              {daysUnsupportedData.gpt.length > 0 && (
                <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-6">
                  <h3 className="text-lg font-semibold text-white mb-4">GPT Models</h3>
                  <p className="text-xs text-[#9099ac] mb-4">Pattern: gpt</p>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={daysUnsupportedData.gpt}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#3c3c4a" />
                      <XAxis
                        dataKey="date"
                        stroke="#9099ac"
                        tick={{ fill: '#9099ac', fontSize: 10 }}
                        tickFormatter={(value) => {
                          const date = new Date(value);
                          return `${date.getMonth() + 1}/${date.getDate()}`;
                        }}
                      />
                      <YAxis
                        stroke="#9099ac"
                        tick={{ fill: '#9099ac', fontSize: 10 }}
                        tickFormatter={(value) => `${value}d`}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1f2228',
                          border: '1px solid #3c3c4a',
                          borderRadius: '8px',
                        }}
                        labelStyle={{ color: '#fff' }}
                        formatter={(value) => [`${value} days`, '']}
                      />
                      <Legend wrapperStyle={{ fontSize: '10px' }} />
                      <Line type="monotone" dataKey="litellm" name="LiteLLM" stroke="#f59e0b" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="eval_proxy" name="Eval Proxy" stroke="#ec4899" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="prod_proxy" name="Prod Proxy" stroke="#14b8a6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="sdk" name="SDK" stroke="#3b82f6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="frontend" name="Frontend" stroke="#22c55e" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="index" name="Index" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="complete" name="Complete" stroke="#ef4444" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Gemini Chart */}
              {daysUnsupportedData.gemini.length > 0 && (
                <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-6">
                  <h3 className="text-lg font-semibold text-white mb-4">Gemini Models</h3>
                  <p className="text-xs text-[#9099ac] mb-4">Pattern: gemini</p>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={daysUnsupportedData.gemini}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#3c3c4a" />
                      <XAxis
                        dataKey="date"
                        stroke="#9099ac"
                        tick={{ fill: '#9099ac', fontSize: 10 }}
                        tickFormatter={(value) => {
                          const date = new Date(value);
                          return `${date.getMonth() + 1}/${date.getDate()}`;
                        }}
                      />
                      <YAxis
                        stroke="#9099ac"
                        tick={{ fill: '#9099ac', fontSize: 10 }}
                        tickFormatter={(value) => `${value}d`}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1f2228',
                          border: '1px solid #3c3c4a',
                          borderRadius: '8px',
                        }}
                        labelStyle={{ color: '#fff' }}
                        formatter={(value) => [`${value} days`, '']}
                      />
                      <Legend wrapperStyle={{ fontSize: '10px' }} />
                      <Line type="monotone" dataKey="litellm" name="LiteLLM" stroke="#f59e0b" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="eval_proxy" name="Eval Proxy" stroke="#ec4899" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="prod_proxy" name="Prod Proxy" stroke="#14b8a6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="sdk" name="SDK" stroke="#3b82f6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="frontend" name="Frontend" stroke="#22c55e" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="index" name="Index" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="complete" name="Complete" stroke="#ef4444" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Open Models Chart */}
              {daysUnsupportedData.open.length > 0 && (
                <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-6">
                  <h3 className="text-lg font-semibold text-white mb-4">Open Models</h3>
                  <p className="text-xs text-[#9099ac] mb-4">Pattern: qwen|minimax|glm|kimi</p>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={daysUnsupportedData.open}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#3c3c4a" />
                      <XAxis
                        dataKey="date"
                        stroke="#9099ac"
                        tick={{ fill: '#9099ac', fontSize: 10 }}
                        tickFormatter={(value) => {
                          const date = new Date(value);
                          return `${date.getMonth() + 1}/${date.getDate()}`;
                        }}
                      />
                      <YAxis
                        stroke="#9099ac"
                        tick={{ fill: '#9099ac', fontSize: 10 }}
                        tickFormatter={(value) => `${value}d`}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1f2228',
                          border: '1px solid #3c3c4a',
                          borderRadius: '8px',
                        }}
                        labelStyle={{ color: '#fff' }}
                        formatter={(value) => [`${value} days`, '']}
                      />
                      <Legend wrapperStyle={{ fontSize: '10px' }} />
                      <Line type="monotone" dataKey="litellm" name="LiteLLM" stroke="#f59e0b" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="eval_proxy" name="Eval Proxy" stroke="#ec4899" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="prod_proxy" name="Prod Proxy" stroke="#14b8a6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="sdk" name="SDK" stroke="#3b82f6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="frontend" name="Frontend" stroke="#22c55e" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="index" name="Index" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="complete" name="Complete" stroke="#ef4444" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Average Chart */}
              {daysUnsupportedData.average.length > 0 && (
                <div className="bg-[#1f2228] rounded-lg border border-[#3c3c4a] p-6 lg:col-span-2 xl:col-span-1">
                  <h3 className="text-lg font-semibold text-white mb-4">Average (All Families)</h3>
                  <p className="text-xs text-[#9099ac] mb-4">Average across Claude, GPT, Gemini, and Open models</p>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={daysUnsupportedData.average}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#3c3c4a" />
                      <XAxis
                        dataKey="date"
                        stroke="#9099ac"
                        tick={{ fill: '#9099ac', fontSize: 10 }}
                        tickFormatter={(value) => {
                          const date = new Date(value);
                          return `${date.getMonth() + 1}/${date.getDate()}`;
                        }}
                      />
                      <YAxis
                        stroke="#9099ac"
                        tick={{ fill: '#9099ac', fontSize: 10 }}
                        tickFormatter={(value) => `${value}d`}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1f2228',
                          border: '1px solid #3c3c4a',
                          borderRadius: '8px',
                        }}
                        labelStyle={{ color: '#fff' }}
                        formatter={(value) => [`${value} days`, '']}
                      />
                      <Legend wrapperStyle={{ fontSize: '10px' }} />
                      <Line type="monotone" dataKey="litellm" name="LiteLLM" stroke="#f59e0b" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="eval_proxy" name="Eval Proxy" stroke="#ec4899" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="prod_proxy" name="Prod Proxy" stroke="#14b8a6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="sdk" name="SDK" stroke="#3b82f6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="frontend" name="Frontend" stroke="#22c55e" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="index" name="Index" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="complete" name="Complete" stroke="#ef4444" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </>
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

import { describe, it, expect } from 'vitest';
import {
  isModelSupportedForAspect,
  computeDaysUnsupported,
  computeFamilyChartData,
  computeAverageChartData,
} from './App';

interface ModelSupport {
  model_id: string;
  release_date: string;
  sdk_support_timestamp: string | null;
  frontend_support_timestamp: string | null;
  index_results_timestamp: string | null;
  eval_proxy_timestamp: string | null;
  prod_proxy_timestamp: string | null;
  litellm_support_timestamp: string | null;
}

describe('isModelSupportedForAspect', () => {
  const testModel: ModelSupport = {
    model_id: 'test-model',
    release_date: '2024-01-01',
    sdk_support_timestamp: '2024-01-05T00:00:00Z',
    frontend_support_timestamp: null,
    index_results_timestamp: '2024-01-03T00:00:00Z',
    eval_proxy_timestamp: '2024-01-10T00:00:00Z',
    prod_proxy_timestamp: null,
    litellm_support_timestamp: '2024-01-02T00:00:00Z',
  };

  it('should return true when model is supported for a single aspect before the check date', () => {
    const checkDate = new Date('2024-01-06');
    expect(isModelSupportedForAspect(testModel, 'sdk', checkDate)).toBe(true);
    expect(isModelSupportedForAspect(testModel, 'litellm', checkDate)).toBe(true);
    expect(isModelSupportedForAspect(testModel, 'index', checkDate)).toBe(true);
  });

  it('should return false when model is not yet supported for a single aspect', () => {
    const checkDate = new Date('2024-01-04');
    expect(isModelSupportedForAspect(testModel, 'sdk', checkDate)).toBe(false);
  });

  it('should return false when support timestamp is null', () => {
    const checkDate = new Date('2024-12-31');
    expect(isModelSupportedForAspect(testModel, 'frontend', checkDate)).toBe(false);
    expect(isModelSupportedForAspect(testModel, 'prod_proxy', checkDate)).toBe(false);
  });

  it('should return false for complete when any aspect is unsupported', () => {
    const checkDate = new Date('2024-12-31');
    // frontend and prod_proxy are null, so complete should be false
    expect(isModelSupportedForAspect(testModel, 'complete', checkDate)).toBe(false);
  });

  it('should return true for complete when all aspects are supported', () => {
    const fullySupported: ModelSupport = {
      model_id: 'fully-supported',
      release_date: '2024-01-01',
      sdk_support_timestamp: '2024-01-02T00:00:00Z',
      frontend_support_timestamp: '2024-01-02T00:00:00Z',
      index_results_timestamp: '2024-01-02T00:00:00Z',
      eval_proxy_timestamp: '2024-01-02T00:00:00Z',
      prod_proxy_timestamp: '2024-01-02T00:00:00Z',
      litellm_support_timestamp: '2024-01-02T00:00:00Z',
    };
    const checkDate = new Date('2024-01-05');
    expect(isModelSupportedForAspect(fullySupported, 'complete', checkDate)).toBe(true);
  });
});

describe('computeDaysUnsupported', () => {
  it('should return empty array when no models match the pattern', () => {
    const models: ModelSupport[] = [
      {
        model_id: 'test-model',
        release_date: '2024-01-01',
        sdk_support_timestamp: null,
        frontend_support_timestamp: null,
        index_results_timestamp: null,
        eval_proxy_timestamp: null,
        prod_proxy_timestamp: null,
        litellm_support_timestamp: null,
      },
    ];
    const result = computeDaysUnsupported(models, /nonexistent/, 'litellm');
    expect(result).toEqual([]);
  });

  it('should count consecutive days unsupported', () => {
    const models: ModelSupport[] = [
      {
        model_id: 'claude-test',
        release_date: '2024-01-01',
        sdk_support_timestamp: null,
        frontend_support_timestamp: null,
        index_results_timestamp: null,
        eval_proxy_timestamp: null,
        prod_proxy_timestamp: null,
        litellm_support_timestamp: '2024-01-05T00:00:00Z',
      },
    ];

    const result = computeDaysUnsupported(models, /claude/, 'litellm');

    // Model released 2024-01-01, supported on 2024-01-05
    // Days 1-4 should increment, day 5+ should be 0
    expect(result.length).toBeGreaterThan(0);

    // Check the first few days
    const day1 = result.find((d) => d.date === '2024-01-01');
    const day2 = result.find((d) => d.date === '2024-01-02');
    const day3 = result.find((d) => d.date === '2024-01-03');
    const day4 = result.find((d) => d.date === '2024-01-04');
    const day5 = result.find((d) => d.date === '2024-01-05');

    expect(day1?.daysUnsupported).toBe(1);
    expect(day2?.daysUnsupported).toBe(2);
    expect(day3?.daysUnsupported).toBe(3);
    expect(day4?.daysUnsupported).toBe(4);
    expect(day5?.daysUnsupported).toBe(0); // Now supported, reset to 0
  });

  it('should keep incrementing if model never gets supported', () => {
    const releaseDate = '2024-06-01';
    const models: ModelSupport[] = [
      {
        model_id: 'gpt-test',
        release_date: releaseDate,
        sdk_support_timestamp: null,
        frontend_support_timestamp: null,
        index_results_timestamp: null,
        eval_proxy_timestamp: null,
        prod_proxy_timestamp: null,
        litellm_support_timestamp: null,
      },
    ];

    const result = computeDaysUnsupported(models, /gpt/, 'litellm');

    // Should have data points starting from release date
    expect(result.length).toBeGreaterThan(0);
    expect(result[0].date).toBe(releaseDate);

    // Days unsupported should be monotonically increasing
    for (let i = 1; i < result.length; i++) {
      expect(result[i].daysUnsupported).toBeGreaterThan(result[i - 1].daysUnsupported);
    }
  });

  it('should handle multiple models - any unsupported keeps counting', () => {
    const models: ModelSupport[] = [
      {
        model_id: 'claude-1',
        release_date: '2024-01-01',
        sdk_support_timestamp: null,
        frontend_support_timestamp: null,
        index_results_timestamp: null,
        eval_proxy_timestamp: null,
        prod_proxy_timestamp: null,
        litellm_support_timestamp: '2024-01-02T00:00:00Z',
      },
      {
        model_id: 'claude-2',
        release_date: '2024-01-03',
        sdk_support_timestamp: null,
        frontend_support_timestamp: null,
        index_results_timestamp: null,
        eval_proxy_timestamp: null,
        prod_proxy_timestamp: null,
        litellm_support_timestamp: '2024-01-10T00:00:00Z',
      },
    ];

    const result = computeDaysUnsupported(models, /claude/, 'litellm');

    // Day 1: claude-1 unsupported -> 1
    // Day 2: claude-1 supported -> 0
    // Day 3: claude-2 released, unsupported -> 1
    // Day 4-9: claude-2 still unsupported -> 2, 3, 4, 5, 6, 7
    // Day 10: claude-2 supported -> 0

    const day1 = result.find((d) => d.date === '2024-01-01');
    const day2 = result.find((d) => d.date === '2024-01-02');
    const day3 = result.find((d) => d.date === '2024-01-03');
    const day10 = result.find((d) => d.date === '2024-01-10');

    expect(day1?.daysUnsupported).toBe(1);
    expect(day2?.daysUnsupported).toBe(0);
    expect(day3?.daysUnsupported).toBe(1);
    expect(day10?.daysUnsupported).toBe(0);
  });
});

describe('computeFamilyChartData', () => {
  it('should return data points with all aspects', () => {
    const models: ModelSupport[] = [
      {
        model_id: 'claude-test',
        release_date: '2024-01-01',
        sdk_support_timestamp: '2024-01-02T00:00:00Z',
        frontend_support_timestamp: '2024-01-03T00:00:00Z',
        index_results_timestamp: '2024-01-04T00:00:00Z',
        eval_proxy_timestamp: '2024-01-05T00:00:00Z',
        prod_proxy_timestamp: '2024-01-06T00:00:00Z',
        litellm_support_timestamp: '2024-01-01T00:00:00Z',
      },
    ];

    const result = computeFamilyChartData(models, /claude/);

    expect(result.length).toBeGreaterThan(0);

    // Check that all aspects are present
    const firstPoint = result[0];
    expect(firstPoint).toHaveProperty('date');
    expect(firstPoint).toHaveProperty('litellm');
    expect(firstPoint).toHaveProperty('eval_proxy');
    expect(firstPoint).toHaveProperty('prod_proxy');
    expect(firstPoint).toHaveProperty('sdk');
    expect(firstPoint).toHaveProperty('frontend');
    expect(firstPoint).toHaveProperty('index');
    expect(firstPoint).toHaveProperty('complete');
  });

  it('should return sampled weekly data points', () => {
    const models: ModelSupport[] = [
      {
        model_id: 'gpt-test',
        release_date: '2024-01-01',
        sdk_support_timestamp: null,
        frontend_support_timestamp: null,
        index_results_timestamp: null,
        eval_proxy_timestamp: null,
        prod_proxy_timestamp: null,
        litellm_support_timestamp: null,
      },
    ];

    const result = computeFamilyChartData(models, /gpt/);

    // Data should be weekly sampled
    if (result.length > 1) {
      const date1 = new Date(result[0].date);
      const date2 = new Date(result[1].date);
      const diffDays = (date2.getTime() - date1.getTime()) / (1000 * 60 * 60 * 24);
      expect(diffDays).toBe(7);
    }
  });
});

describe('computeAverageChartData', () => {
  it('should compute average across families', () => {
    const familyData = {
      claude: [
        { date: '2024-01-01', litellm: 10, eval_proxy: 0, prod_proxy: 0, sdk: 0, frontend: 0, index: 0, complete: 10 },
      ],
      gpt: [
        { date: '2024-01-01', litellm: 20, eval_proxy: 0, prod_proxy: 0, sdk: 0, frontend: 0, index: 0, complete: 20 },
      ],
    };

    const result = computeAverageChartData(familyData);

    expect(result.length).toBe(1);
    expect(result[0].date).toBe('2024-01-01');
    expect(result[0].litellm).toBe(15); // (10 + 20) / 2
    expect(result[0].complete).toBe(15); // (10 + 20) / 2
  });

  it('should handle missing dates across families', () => {
    const familyData = {
      claude: [
        { date: '2024-01-01', litellm: 10, eval_proxy: 0, prod_proxy: 0, sdk: 0, frontend: 0, index: 0, complete: 10 },
        { date: '2024-01-08', litellm: 5, eval_proxy: 0, prod_proxy: 0, sdk: 0, frontend: 0, index: 0, complete: 5 },
      ],
      gpt: [
        { date: '2024-01-08', litellm: 15, eval_proxy: 0, prod_proxy: 0, sdk: 0, frontend: 0, index: 0, complete: 15 },
      ],
    };

    const result = computeAverageChartData(familyData);

    // Should have dates from both families
    const dates = result.map((r) => r.date);
    expect(dates).toContain('2024-01-01');
    expect(dates).toContain('2024-01-08');

    // On 2024-01-01, only claude has data
    const jan1 = result.find((r) => r.date === '2024-01-01');
    expect(jan1?.litellm).toBe(10); // Only claude

    // On 2024-01-08, both have data
    const jan8 = result.find((r) => r.date === '2024-01-08');
    expect(jan8?.litellm).toBe(10); // (5 + 15) / 2
  });
});

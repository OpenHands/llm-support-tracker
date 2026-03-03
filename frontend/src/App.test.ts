import { describe, it, expect } from 'vitest';
import {
  isModelSupportedForAspect,
  computeDaysUnsupported,
  computeFamilyChartData,
  computeAverageChartData,
  applyRollingAverage,
  getWeeklySampleDates,
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

describe('applyRollingAverage', () => {
  it('should compute 30-day rolling average', () => {
    const data = new Map<string, number>([
      ['2024-01-01', 0],
      ['2024-01-02', 10],
      ['2024-01-03', 20],
      ['2024-01-04', 30],
    ]);
    const sortedDates = ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04'];

    const result = applyRollingAverage(data, sortedDates, 30);

    // Day 1: avg of [0] = 0
    expect(result.get('2024-01-01')).toBe(0);
    // Day 2: avg of [0, 10] = 5
    expect(result.get('2024-01-02')).toBe(5);
    // Day 3: avg of [0, 10, 20] = 10
    expect(result.get('2024-01-03')).toBe(10);
    // Day 4: avg of [0, 10, 20, 30] = 15
    expect(result.get('2024-01-04')).toBe(15);
  });

  it('should only include values within the window', () => {
    const data = new Map<string, number>([
      ['2024-01-01', 100],
      ['2024-02-05', 10], // 35 days later
    ]);
    const sortedDates = ['2024-01-01', '2024-02-05'];

    const result = applyRollingAverage(data, sortedDates, 30);

    // Day 1: avg of [100] = 100
    expect(result.get('2024-01-01')).toBe(100);
    // Feb 5: only includes itself (Jan 1 is > 30 days ago)
    expect(result.get('2024-02-05')).toBe(10);
  });
});

describe('getWeeklySampleDates', () => {
  it('should return Sundays between start and end dates', () => {
    // 2024-01-01 is a Monday
    const result = getWeeklySampleDates('2024-01-01', '2024-01-31');

    // First Sunday after Jan 1, 2024 is Jan 7
    expect(result[0]).toBe('2024-01-07');
    expect(result[1]).toBe('2024-01-14');
    expect(result[2]).toBe('2024-01-21');
    expect(result[3]).toBe('2024-01-28');
    // Should include end date
    expect(result[result.length - 1]).toBe('2024-01-31');
  });

  it('should include start date if it is a Sunday', () => {
    // 2024-01-07 is a Sunday
    const result = getWeeklySampleDates('2024-01-07', '2024-01-21');

    expect(result[0]).toBe('2024-01-07');
    expect(result[1]).toBe('2024-01-14');
    expect(result[2]).toBe('2024-01-21');
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

  it('should use provided sample dates for consistent alignment', () => {
    const models: ModelSupport[] = [
      {
        model_id: 'claude-test',
        release_date: '2024-01-01',
        sdk_support_timestamp: null,
        frontend_support_timestamp: null,
        index_results_timestamp: null,
        eval_proxy_timestamp: null,
        prod_proxy_timestamp: null,
        litellm_support_timestamp: null,
      },
    ];

    const sampleDates = ['2024-01-07', '2024-01-14', '2024-01-21'];
    const result = computeFamilyChartData(models, /claude/, sampleDates);

    // Should use the provided sample dates
    const dates = result.map((r) => r.date);
    expect(dates).toEqual(sampleDates);
  });

  it('should apply 30-day rolling average to smooth data', () => {
    const models: ModelSupport[] = [
      {
        model_id: 'claude-test',
        release_date: '2024-01-01',
        sdk_support_timestamp: null,
        frontend_support_timestamp: null,
        index_results_timestamp: null,
        eval_proxy_timestamp: null,
        prod_proxy_timestamp: null,
        // Supported on day 15, so raw values would be 1,2,3...14,0,0,0...
        litellm_support_timestamp: '2024-01-15T00:00:00Z',
      },
    ];

    const sampleDates = ['2024-01-07', '2024-01-14', '2024-01-21', '2024-01-28'];
    const result = computeFamilyChartData(models, /claude/, sampleDates);

    // With rolling average, the values should be smoothed
    // Jan 7: avg of days 1-7 (raw values 1,2,3,4,5,6,7) = 4
    // Jan 14: avg of days 1-14 (raw values 1-14) = 7.5 -> 8
    // Jan 21: avg of days 1-21 (raw 1-14, then 0s for 15-21) = sum(1-14)/21 = 105/21 = 5
    // The exact values depend on the 30-day window, but they should be smoothed
    expect(result.length).toBe(4);
    
    // Value on Jan 21 should be less than Jan 14 due to smoothing after support
    const jan14 = result.find((r) => r.date === '2024-01-14');
    const jan21 = result.find((r) => r.date === '2024-01-21');
    expect(jan21!.litellm).toBeLessThan(jan14!.litellm);
  });
});

describe('computeAverageChartData', () => {
  it('should compute average across families with same dates', () => {
    const familyData = {
      claude: [
        { date: '2024-01-07', litellm: 10, eval_proxy: 0, prod_proxy: 0, sdk: 0, frontend: 0, index: 0, complete: 10 },
        { date: '2024-01-14', litellm: 20, eval_proxy: 0, prod_proxy: 0, sdk: 0, frontend: 0, index: 0, complete: 20 },
      ],
      gpt: [
        { date: '2024-01-07', litellm: 30, eval_proxy: 0, prod_proxy: 0, sdk: 0, frontend: 0, index: 0, complete: 30 },
        { date: '2024-01-14', litellm: 40, eval_proxy: 0, prod_proxy: 0, sdk: 0, frontend: 0, index: 0, complete: 40 },
      ],
    };

    const result = computeAverageChartData(familyData);

    expect(result.length).toBe(2);
    
    const jan7 = result.find((r) => r.date === '2024-01-07');
    expect(jan7?.litellm).toBe(20); // (10 + 30) / 2
    expect(jan7?.complete).toBe(20); // (10 + 30) / 2
    
    const jan14 = result.find((r) => r.date === '2024-01-14');
    expect(jan14?.litellm).toBe(30); // (20 + 40) / 2
    expect(jan14?.complete).toBe(30); // (20 + 40) / 2
  });

  it('should only include dates in common range across all families', () => {
    const familyData = {
      claude: [
        { date: '2024-01-07', litellm: 10, eval_proxy: 0, prod_proxy: 0, sdk: 0, frontend: 0, index: 0, complete: 10 },
        { date: '2024-01-14', litellm: 20, eval_proxy: 0, prod_proxy: 0, sdk: 0, frontend: 0, index: 0, complete: 20 },
        { date: '2024-01-21', litellm: 30, eval_proxy: 0, prod_proxy: 0, sdk: 0, frontend: 0, index: 0, complete: 30 },
      ],
      gpt: [
        // GPT starts later
        { date: '2024-01-14', litellm: 40, eval_proxy: 0, prod_proxy: 0, sdk: 0, frontend: 0, index: 0, complete: 40 },
        { date: '2024-01-21', litellm: 50, eval_proxy: 0, prod_proxy: 0, sdk: 0, frontend: 0, index: 0, complete: 50 },
      ],
    };

    const result = computeAverageChartData(familyData);

    // Should only include dates where both families have data (Jan 14 and Jan 21)
    const dates = result.map((r) => r.date);
    expect(dates).not.toContain('2024-01-07'); // Claude only
    expect(dates).toContain('2024-01-14');
    expect(dates).toContain('2024-01-21');
    
    const jan14 = result.find((r) => r.date === '2024-01-14');
    expect(jan14?.litellm).toBe(30); // (20 + 40) / 2
  });
});

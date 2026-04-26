import { chatIteration, summarize } from './lib/chat.js';

const dataset = JSON.parse(open('../datasets/onboarding_questions.json')).cases;

export const options = {
  summaryTrendStats: ['min', 'avg', 'med', 'p(50)', 'p(95)', 'p(99)', 'max'],
  thresholds: {
    http_req_failed: ['rate<0.05'],
    rag_failure_rate: ['rate<0.05'],
    http_req_duration: ['p(99)<8000'],
  },
  scenarios: {
    spike: {
      executor: 'ramping-vus',
      stages: [
        { duration: __ENV.BASELINE_DURATION || '30s', target: Number(__ENV.BASELINE_VUS || '5') },
        { duration: __ENV.SPIKE_RAMP || '20s', target: Number(__ENV.SPIKE_VUS || '100') },
        { duration: __ENV.SPIKE_HOLD || '1m', target: Number(__ENV.SPIKE_VUS || '100') },
        { duration: __ENV.RECOVERY_RAMP || '20s', target: Number(__ENV.BASELINE_VUS || '5') },
        { duration: __ENV.RECOVERY_HOLD || '30s', target: Number(__ENV.BASELINE_VUS || '5') },
      ],
      gracefulRampDown: '30s',
    },
  },
};

export default function () {
  chatIteration(dataset);
}

export function handleSummary(data) {
  return summarize(data, __ENV.SUMMARY_OUT || 'benchmarks/results/k6-spike-summary.json');
}

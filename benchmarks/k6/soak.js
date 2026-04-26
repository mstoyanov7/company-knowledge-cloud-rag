import { chatIteration, summarize } from './lib/chat.js';

const dataset = JSON.parse(open('../datasets/onboarding_questions.json')).cases;

export const options = {
  summaryTrendStats: ['min', 'avg', 'med', 'p(50)', 'p(95)', 'p(99)', 'max'],
  thresholds: {
    http_req_failed: ['rate<0.02'],
    rag_failure_rate: ['rate<0.02'],
    http_req_duration: ['p(95)<3000'],
  },
  scenarios: {
    soak: {
      executor: 'constant-vus',
      vus: Number(__ENV.SOAK_VUS || '10'),
      duration: __ENV.SOAK_DURATION || '30m',
      gracefulStop: '1m',
    },
  },
};

export default function () {
  chatIteration(dataset);
}

export function handleSummary(data) {
  return summarize(data, __ENV.SUMMARY_OUT || 'benchmarks/results/k6-soak-summary.json');
}

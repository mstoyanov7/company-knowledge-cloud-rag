import { chatIteration, summarize } from './lib/chat.js';

const dataset = JSON.parse(open('../datasets/onboarding_questions.json')).cases;

export const options = {
  summaryTrendStats: ['min', 'avg', 'med', 'p(50)', 'p(95)', 'p(99)', 'max'],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    rag_failure_rate: ['rate<0.01'],
    http_req_duration: ['p(95)<1500'],
  },
  scenarios: {
    smoke: {
      executor: 'shared-iterations',
      vus: Number(__ENV.VUS || '1'),
      iterations: Number(__ENV.ITERATIONS || '10'),
      maxDuration: __ENV.MAX_DURATION || '2m',
    },
  },
};

export default function () {
  chatIteration(dataset);
}

export function handleSummary(data) {
  return summarize(data, __ENV.SUMMARY_OUT || 'benchmarks/results/k6-smoke-summary.json');
}

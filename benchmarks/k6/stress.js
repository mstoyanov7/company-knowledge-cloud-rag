import { chatIteration, summarize } from './lib/chat.js';

const dataset = JSON.parse(open('../datasets/onboarding_questions.json')).cases;

export const options = {
  summaryTrendStats: ['min', 'avg', 'med', 'p(50)', 'p(95)', 'p(99)', 'max'],
  thresholds: {
    http_req_failed: ['rate<0.02'],
    rag_failure_rate: ['rate<0.02'],
    http_req_duration: ['p(95)<3000', 'p(99)<5000'],
  },
  scenarios: {
    stress: {
      executor: 'ramping-vus',
      stages: [
        { duration: __ENV.RAMP_UP || '2m', target: Number(__ENV.STRESS_VUS || '25') },
        { duration: __ENV.HOLD || '5m', target: Number(__ENV.STRESS_VUS || '25') },
        { duration: __ENV.RAMP_DOWN || '1m', target: 0 },
      ],
      gracefulRampDown: '30s',
    },
  },
};

export default function () {
  chatIteration(dataset);
}

export function handleSummary(data) {
  return summarize(data, __ENV.SUMMARY_OUT || 'benchmarks/results/k6-stress-summary.json');
}

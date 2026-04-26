import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

export const answerLatency = new Trend('rag_answer_latency_ms', true);
export const retrievalLatency = new Trend('rag_retrieval_latency_ms', true);
export const completionLatency = new Trend('rag_completion_latency_ms', true);
export const freshnessDelay = new Trend('rag_freshness_delay_ms', true);
export const citationCount = new Trend('rag_citation_count');
export const failureRate = new Rate('rag_failure_rate');
export const chatThroughput = new Counter('rag_chat_requests_total');

const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8080').replace(/\/$/, '');
const API_KEY = __ENV.RAG_API_KEY || '';
const THINK_TIME_SECONDS = Number(__ENV.THINK_TIME_SECONDS || '1');
const SOURCE_FILTERS = (__ENV.SOURCE_FILTERS || '').split(',').map((item) => item.trim()).filter(Boolean);
const RUN_ID = __ENV.BENCHMARK_RUN_ID || `k6-${Date.now()}`;

export function chatIteration(dataset) {
  const benchmarkCase = dataset[(__ITER + __VU) % dataset.length];
  const payload = {
    question: benchmarkCase.question,
    user_context: benchmarkCase.user_context,
    source_filters: SOURCE_FILTERS,
    top_k: benchmarkCase.top_k || Number(__ENV.TOP_K || '3'),
  };
  const headers = {
    'Content-Type': 'application/json',
    'X-Benchmark-Run-Id': RUN_ID,
    'X-Benchmark-Case-Id': benchmarkCase.case_id,
  };
  if (API_KEY) {
    headers.Authorization = `Bearer ${API_KEY}`;
  }

  const response = http.post(`${BASE_URL}/api/v1/answer`, JSON.stringify(payload), {
    headers,
    tags: { case_id: benchmarkCase.case_id },
    timeout: __ENV.REQUEST_TIMEOUT || '60s',
  });

  chatThroughput.add(1);
  const ok = check(response, {
    'status is 200': (res) => res.status === 200,
    'response has answer': (res) => Boolean(jsonValue(res, 'answer')),
    'response has metadata': (res) => Boolean(jsonValue(res, 'metadata')),
  });
  failureRate.add(!ok);

  if (ok) {
    const body = response.json();
    const metadata = body.metadata || {};
    answerLatency.add(numberOrZero(metadata.duration_ms));
    retrievalLatency.add(numberOrZero(metadata.retrieval_latency_ms || body.retrieval_meta?.duration_ms));
    completionLatency.add(numberOrZero(metadata.completion_latency_ms));
    citationCount.add(numberOrZero(metadata.citation_count ?? (body.citations || []).length));
    if (metadata.freshness_delay_ms !== null && metadata.freshness_delay_ms !== undefined) {
      freshnessDelay.add(numberOrZero(metadata.freshness_delay_ms));
    }
  }

  sleep(THINK_TIME_SECONDS);
}

export function summarize(data, outputPath) {
  return {
    stdout: JSON.stringify(data.metrics, null, 2),
    [outputPath || 'benchmarks/results/k6-summary.json']: JSON.stringify(data, null, 2),
  };
}

function jsonValue(response, key) {
  try {
    return response.json(key);
  } catch {
    return null;
  }
}

function numberOrZero(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

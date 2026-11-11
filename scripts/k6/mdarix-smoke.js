// Run only against an approved non-production target:
// k6 run -e BASE_URL=http://127.0.0.1:8007 scripts/k6/mdarix-smoke.js
import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500", "p(99)<1000"],
    // B6a: the complaint page and the story, held to the read SLO (p95 <= 500 ms) when a session is given.
    "http_req_duration{page:complaint}": ["p(95)<500"],
    "http_req_duration{page:story}": ["p(95)<500"],
  },
  scenarios: { smoke: { executor: "constant-vus", vus: 2, duration: "30s" } },
};

export default function () {
  const base = __ENV.BASE_URL || "http://127.0.0.1:8007";
  const live = http.get(`${base}/health/live`);
  check(live, { "live endpoint is healthy": (r) => r.status === 200 });
  // The public status (served by the API and through Caddy alike): ok or degraded is 200, down is 503 and fails.
  // /health/ready is internal: Caddy answers 404 for it.
  const status = http.get(`${base}/health/status`);
  check(status, { "status endpoint is ok or degraded": (r) => r.status === 200 });
  // A trial's session cookie (-e SESSION=...), from a test trial on that server, never a customer's.
  if (__ENV.SESSION) {
    const params = (page) => ({ headers: { Cookie: `mdarix_session=${__ENV.SESSION}` }, tags: { page } });
    const complaint = http.get(`${base}/api/v1/oversight/events/SAMPLE-RV-11`, params("complaint"));
    check(complaint, { "complaint page answers": (r) => r.status === 200 });
    const story = http.get(`${base}/api/v1/trial/one-story`, params("story"));
    check(story, { "story answers": (r) => r.status === 200 });
  }
  sleep(1);
}

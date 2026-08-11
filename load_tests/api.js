import http from "k6/http";
import { check, fail, sleep } from "k6";

const BASE_URL = (__ENV.BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const PROFILE = __ENV.PROFILE || "authenticated";
const VUS = positiveInteger("VUS", 5);
const DURATION = __ENV.DURATION || "30s";
const REFRESH_EVERY = positiveInteger("REFRESH_EVERY", 20);
const PASSWORD = __ENV.LOAD_TEST_PASSWORD || "local-load-test-password";
const RUN_ID = (__ENV.RUN_ID || `${Date.now()}`)
  .replace(/[^a-zA-Z0-9_-]/g, "")
  .slice(0, 40);

if (!["health", "authenticated"].includes(PROFILE)) {
  throw new Error("PROFILE must be health or authenticated");
}

assertSafeTarget(BASE_URL);

export const options = {
  vus: VUS,
  duration: DURATION,
  discardResponseBodies: true,
  thresholds: {
    checks: ["rate>0.99"],
    "http_req_failed{phase:workload}": ["rate<0.01"],
    "http_req_duration{phase:workload}": ["p(95)<500", "p(99)<1000"],
  },
};

function positiveInteger(name, fallback) {
  const value = Number.parseInt(__ENV[name] || `${fallback}`, 10);
  if (!Number.isInteger(value) || value < 1) {
    throw new Error(`${name} must be a positive integer`);
  }
  return value;
}

function assertSafeTarget(value) {
  const parsed = value.match(/^https?:\/\/(\[[^\]]+\]|[^/:]+)(?::\d+)?(?:\/.*)?$/i);
  if (!parsed) {
    throw new Error("BASE_URL must be an absolute HTTP(S) URL");
  }
  const hostname = parsed[1].toLowerCase();
  const localHosts = new Set(["localhost", "127.0.0.1", "[::1]", "host.docker.internal"]);
  if (!localHosts.has(hostname) && __ENV.ALLOW_REMOTE_TARGET !== "true") {
    throw new Error(
      "Refusing a remote target. Set ALLOW_REMOTE_TARGET=true only for an authorized non-production environment.",
    );
  }
}

function workloadTags(endpoint) {
  return { tags: { phase: "workload", endpoint } };
}

export function setup() {
  const ready = http.get(`${BASE_URL}/health/ready`, workloadTags("readiness"));
  if (!check(ready, { "target is ready": (response) => response.status === 200 })) {
    fail(`Target is not ready: HTTP ${ready.status}`);
  }

  if (PROFILE === "health") {
    return { users: [] };
  }

  const users = [];
  for (let index = 1; index <= VUS; index += 1) {
    const username = `load_${RUN_ID}_${index}`;
    const registration = http.post(
      `${BASE_URL}/register/`,
      JSON.stringify({ username, password: PASSWORD }),
      { headers: { "Content-Type": "application/json" }, tags: { phase: "setup", endpoint: "register" } },
    );
    if (!check(registration, { "load-test user registered": (response) => response.status === 200 })) {
      fail(`Could not register ${username}: HTTP ${registration.status}`);
    }
    users.push(username);
  }
  return { users };
}

let tokens;

function login(username) {
  const response = http.post(
    `${BASE_URL}/login/`,
    { username, password: PASSWORD },
    {
      headers: { "X-Device-Name": `k6-vu-${__VU}` },
      tags: { phase: "setup", endpoint: "login" },
      responseType: "text",
    },
  );
  if (!check(response, { "load-test user logged in": (result) => result.status === 200 })) {
    fail(`Could not log in ${username}: HTTP ${response.status}`);
  }
  return response.json();
}

function authenticatedIteration(data) {
  if (!tokens) {
    tokens = login(data.users[__VU - 1]);
  }

  const me = http.get(`${BASE_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
    ...workloadTags("auth_me"),
  });
  check(me, { "authenticated read succeeds": (response) => response.status === 200 });

  if (__ITER > 0 && __ITER % REFRESH_EVERY === 0) {
    const rotated = http.post(
      `${BASE_URL}/auth/refresh`,
      JSON.stringify({ refresh_token: tokens.refresh_token }),
      {
        headers: { "Content-Type": "application/json" },
        ...workloadTags("refresh"),
        responseType: "text",
      },
    );
    if (check(rotated, { "refresh rotation succeeds": (response) => response.status === 200 })) {
      tokens = rotated.json();
    }
  }
}

export default function (data) {
  if (PROFILE === "health") {
    const response = http.get(`${BASE_URL}/health/live`, workloadTags("liveness"));
    check(response, { "liveness succeeds": (result) => result.status === 200 });
  } else {
    authenticatedIteration(data);
  }
  sleep(0.1);
}


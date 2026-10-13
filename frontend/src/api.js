import axios from "axios";

const client = axios.create({
  baseURL: "/api",
  timeout: 30000,
});

export function setSessionToken(token) {
  client.defaults.headers.common.Authorization = token ? `Bearer ${token}` : undefined;
}

export async function login({ email, password }) {
  const { data } = await client.post("/auth/login", { email, password });
  return data;
}

export async function register({ email, password }) {
  const { data } = await client.post("/auth/register", { email, password });
  return data;
}

export async function roleLogin({ role, pin }) {
  const { data } = await client.post("/auth/role-login", { role, pin });
  return data;
}

export async function fetchRoles() {
  const { data } = await client.get("/roles");
  return data;
}

export async function fetchConfig() {
  const { data } = await client.get("/config");
  return data;
}

export async function postQuery({ question, role, contextQuestion, apiKey, provider }) {
  const { data } = await client.post("/query", {
    question,
    role,
    context_question: contextQuestion || null,
    api_key: apiKey || null,
    provider: provider || null,
  });
  return data;
}

export async function fetchIncidents({ role = "engineer", limit = 50 } = {}) {
  const { data } = await client.get("/incidents", { params: { role, limit } });
  return data;
}

export async function fetchAnalytics() {
  const { data } = await client.get("/analytics");
  return data;
}

export async function fetchKnowledgeGraphTopology() {
  const { data } = await client.get("/knowledge-graph/topology");
  return data;
}

export async function reloadDataset() {
  const { data } = await client.post("/dataset/reload");
  return data;
}

export async function fetchLiveIncidentStatus() {
  const { data } = await client.get("/live-incidents/status");
  return data;
}

export async function fetchLiveIncidents(limit = 25) {
  const { data } = await client.get("/live-incidents", { params: { limit } });
  return data;
}

export async function analyzeLiveIncidents(question) {
  const { data } = await client.post("/live-incidents/analyze", { question });
  return data;
}

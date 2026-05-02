import express, { Request, Response } from "express";
import fs from "fs";
import path from "path";

type StorePayload = {
  traces: Record<string, unknown>;
  feedback: Record<string, unknown>;
  costs: Record<string, unknown>;
  events: Record<string, { entityType: string; payload: unknown; updatedAt: number }>;
};

const PORT = Number(process.env.ADAPTER_PORT || "4010");
const API_KEY = process.env.ADAPTER_API_KEY || "";
const DATA_FILE = process.env.ADAPTER_DATA_FILE || path.join(process.cwd(), "adapter-data.json");
const ALLOWED_ENTITY_TYPES = new Set(["trace", "feedback", "cost"]);
const MAX_LIMIT = 200;

const ensureStore = (): StorePayload => {
  if (!fs.existsSync(DATA_FILE)) {
    const seed: StorePayload = { traces: {}, feedback: {}, costs: {}, events: {} };
    fs.mkdirSync(path.dirname(DATA_FILE), { recursive: true });
    fs.writeFileSync(DATA_FILE, JSON.stringify(seed, null, 2), "utf-8");
    return seed;
  }
  try {
    const raw = fs.readFileSync(DATA_FILE, "utf-8");
    const parsed = JSON.parse(raw) as StorePayload;
    return {
      traces: parsed.traces || {},
      feedback: parsed.feedback || {},
      costs: parsed.costs || {},
      events: parsed.events || {},
    };
  } catch {
    return { traces: {}, feedback: {}, costs: {}, events: {} };
  }
};

let state = ensureStore();

const persist = (): void => {
  fs.writeFileSync(DATA_FILE, JSON.stringify(state, null, 2), "utf-8");
};

const requireKey = (req: Request, res: Response, next: () => void): void => {
  if (!API_KEY) {
    next();
    return;
  }
  const key = req.header("X-Adapter-Key") || "";
  if (key !== API_KEY) {
    res.status(401).json({ ok: false, error: "Invalid adapter key" });
    return;
  }
  next();
};

const app = express();
app.use(express.json({ limit: "1mb" }));
app.use(requireKey);

app.get("/sync/health", (_req, res) => {
  res.json({ ok: true, service: "supportoid-convex-adapter" });
});

app.post("/sync/event", (req, res) => {
  const eventId = String(req.body?.eventId || "").trim();
  const entityType = String(req.body?.entityType || "").trim();
  const payload = req.body?.payload;

  if (!eventId || !entityType || typeof payload === "undefined") {
    res.status(400).json({ ok: false, error: "eventId, entityType, payload are required" });
    return;
  }
  if (!ALLOWED_ENTITY_TYPES.has(entityType)) {
    res.status(400).json({ ok: false, error: "Unsupported entityType" });
    return;
  }
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    res.status(400).json({ ok: false, error: "payload must be a JSON object" });
    return;
  }
  if (eventId.length > 120 || entityType.length > 40) {
    res.status(400).json({ ok: false, error: "eventId or entityType too long" });
    return;
  }

  // Deterministic idempotency: same eventId always upserts one canonical row.
  state.events[eventId] = { entityType, payload, updatedAt: Date.now() };

  if (entityType === "trace") {
    const sid = String((payload as Record<string, unknown>)?.session_id || eventId);
    state.traces[sid] = payload;
  } else if (entityType === "feedback") {
    const fid = String((payload as Record<string, unknown>)?.feedback_id || eventId);
    state.feedback[fid] = payload;
  } else if (entityType === "cost") {
    const cid = String((payload as Record<string, unknown>)?.conversation_id || eventId);
    state.costs[cid] = payload;
  }

  persist();
  res.status(202).json({ ok: true, eventId, entityType });
});

app.get("/data/traces", (req, res) => {
  const requested = Number(req.query.limit || "50");
  const limit = Math.min(MAX_LIMIT, Math.max(1, requested));
  const traces = Object.values(state.traces).slice(0, limit);
  res.json({ traces });
});

app.get("/data/traces/:sessionId", (req, res) => {
  const sessionId = String(req.params.sessionId || "");
  const trace = state.traces[sessionId];
  if (!trace) {
    res.status(404).json({ ok: false, error: "Trace not found" });
    return;
  }
  res.json(trace);
});

app.get("/data/costs", (_req, res) => {
  res.json({ costs: Object.values(state.costs) });
});

app.listen(PORT, () => {
  // eslint-disable-next-line no-console
  console.log(`[supportoid-convex-adapter] listening on ${PORT}`);
});

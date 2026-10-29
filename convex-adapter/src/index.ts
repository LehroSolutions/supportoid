import express, { Request, Response } from 'express';
import fs from 'fs';
import path from 'path';
import { randomUUID, timingSafeEqual } from 'crypto';
import { isDeepStrictEqual } from 'util';

type StorePayload = {
  traces: Record<string, unknown>;
  feedback: Record<string, unknown>;
  costs: Record<string, unknown>;
  events: Record<string, { entityType: string; payload: unknown; updatedAt: number }>;
};

const PORT = Number(process.env.ADAPTER_PORT || '4010');
const HOST = process.env.ADAPTER_HOST || '127.0.0.1';
const API_KEY = process.env.ADAPTER_API_KEY || '';
const DATA_FILE = process.env.ADAPTER_DATA_FILE || path.join(process.cwd(), 'adapter-data.json');
const ALLOWED_ENTITY_TYPES = new Set(['trace', 'feedback', 'cost']);
const MAX_LIMIT = 200;
const unsafeKeys = new Set(['__proto__', 'constructor', 'prototype']);

if (!Number.isInteger(PORT) || PORT < 1 || PORT > 65535) throw new Error('Invalid ADAPTER_PORT');
if (
  (process.env.NODE_ENV === 'production' || !['127.0.0.1', 'localhost', '::1'].includes(HOST)) &&
  API_KEY.length < 32
) {
  throw new Error(
    'A minimum 32-character ADAPTER_API_KEY is required for production or a public bind',
  );
}

function persist(next: StorePayload): void {
  const temporary = `${DATA_FILE}.${randomUUID()}.tmp`;
  try {
    const descriptor = fs.openSync(temporary, 'wx', 0o600);
    try {
      fs.writeFileSync(descriptor, JSON.stringify(next, null, 2), 'utf-8');
      fs.fsyncSync(descriptor);
    } finally {
      fs.closeSync(descriptor);
    }
    fs.renameSync(temporary, DATA_FILE);
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
  }
}

const ensureStore = (): StorePayload => {
  if (!fs.existsSync(DATA_FILE)) {
    const seed: StorePayload = { traces: {}, feedback: {}, costs: {}, events: {} };
    fs.mkdirSync(path.dirname(DATA_FILE), { recursive: true });
    persist(seed);
    return seed;
  }
  try {
    const raw = fs.readFileSync(DATA_FILE, 'utf-8');
    const parsed = JSON.parse(raw) as StorePayload;
    if (
      !parsed ||
      typeof parsed !== 'object' ||
      Array.isArray(parsed) ||
      ['traces', 'feedback', 'costs', 'events'].some((key) => {
        const value = parsed[key as keyof StorePayload];
        return value !== undefined && (!value || typeof value !== 'object' || Array.isArray(value));
      })
    )
      throw new Error('Invalid store shape');
    return {
      traces: parsed.traces || {},
      feedback: parsed.feedback || {},
      costs: parsed.costs || {},
      events: parsed.events || {},
    };
  } catch {
    throw new Error('Adapter data cannot be read. Restore a validated backup before restarting.');
  }
};

let state = ensureStore();

const requireKey = (req: Request, res: Response, next: () => void): void => {
  if (!API_KEY) {
    next();
    return;
  }
  const key = req.header('X-Adapter-Key') || '';
  const actual = Buffer.from(key);
  const expected = Buffer.from(API_KEY);
  if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) {
    res.status(401).json({ ok: false, error: 'Invalid adapter key' });
    return;
  }
  next();
};

const app = express();
app.use(express.json({ limit: '1mb' }));
app.use(requireKey);

app.get('/sync/health', (_req, res) => {
  res.json({ ok: true, service: 'supportoid-convex-adapter' });
});

app.post('/sync/event', (req, res) => {
  const eventId = String(req.body?.eventId || '').trim();
  const entityType = String(req.body?.entityType || '').trim();
  const payload = req.body?.payload;

  if (!eventId || !entityType || typeof payload === 'undefined') {
    res.status(400).json({ ok: false, error: 'eventId, entityType, payload are required' });
    return;
  }
  if (!ALLOWED_ENTITY_TYPES.has(entityType)) {
    res.status(400).json({ ok: false, error: 'Unsupported entityType' });
    return;
  }
  if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
    res.status(400).json({ ok: false, error: 'payload must be a JSON object' });
    return;
  }
  if (eventId.length > 120 || entityType.length > 40 || unsafeKeys.has(eventId)) {
    res.status(400).json({ ok: false, error: 'eventId or entityType too long' });
    return;
  }

  const previous = Object.prototype.hasOwnProperty.call(state.events, eventId)
    ? state.events[eventId]
    : undefined;
  if (previous) {
    if (previous.entityType !== entityType || !isDeepStrictEqual(previous.payload, payload)) {
      res.status(409).json({ ok: false, error: 'eventId already belongs to different content' });
      return;
    }
    res.status(202).json({ ok: true, eventId, entityType });
    return;
  }
  const next = structuredClone(state);
  next.events[eventId] = { entityType, payload, updatedAt: Date.now() };
  const keyName =
    entityType === 'trace'
      ? 'session_id'
      : entityType === 'feedback'
        ? 'feedback_id'
        : 'conversation_id';
  const entityId = String((payload as Record<string, unknown>)[keyName] || eventId);
  if (unsafeKeys.has(entityId) || entityId.length > 120) {
    res.status(400).json({ ok: false, error: 'Invalid entity identifier' });
    return;
  }

  if (entityType === 'trace') {
    next.traces[entityId] = payload;
  } else if (entityType === 'feedback') {
    next.feedback[entityId] = payload;
  } else if (entityType === 'cost') {
    next.costs[entityId] = payload;
  }

  persist(next);
  state = next;
  res.status(202).json({ ok: true, eventId, entityType });
});

app.get('/data/traces', (req, res) => {
  const requested = Number(req.query.limit || '50');
  if (!Number.isInteger(requested) || requested < 1) {
    res.status(400).json({ ok: false, error: 'limit must be a positive integer' });
    return;
  }
  const limit = Math.min(MAX_LIMIT, Math.max(1, requested));
  const traces = Object.values(state.traces).slice(0, limit);
  res.json({ traces });
});

app.get('/data/traces/:sessionId', (req, res) => {
  const sessionId = String(req.params.sessionId || '');
  const trace = Object.prototype.hasOwnProperty.call(state.traces, sessionId)
    ? state.traces[sessionId]
    : undefined;
  if (!trace) {
    res.status(404).json({ ok: false, error: 'Trace not found' });
    return;
  }
  res.json(trace);
});

app.get('/data/costs', (_req, res) => {
  res.json({ costs: Object.values(state.costs) });
});

app.use(
  (
    error: { status?: number; type?: string },
    _req: Request,
    res: Response,
    _next: express.NextFunction,
  ) => {
    const status = error.status === 413 ? 413 : error.status === 400 ? 400 : 500;
    res.status(status).json({
      ok: false,
      error: status === 500 ? 'Adapter request failed' : 'Invalid request body',
    });
  },
);

app.listen(PORT, HOST, () => {
  // eslint-disable-next-line no-console
  console.log(`[supportoid-convex-adapter] listening on ${HOST}:${PORT}`);
});

import type { Provider } from "./capture.js";

export type RolloutPercent = 1 | 5 | 25 | 100;

export interface BoundedConfigPatch {
  readonly model?: string;
  readonly reasoningEffort?: string;
  readonly maxTokens?: number;
}

export interface DeploymentPolicy {
  readonly id: string;
  readonly provider: Provider;
  readonly callSiteId: string;
  readonly sourceConfigId: string;
  readonly rolloutPercent: RolloutPercent;
  readonly patch: BoundedConfigPatch;
}

export interface ConfigIdentity {
  readonly systemHash: string;
  readonly toolsHash: string;
  readonly paramsHash: string;
  readonly configId: string;
}

export interface PreparedRequest {
  readonly body: string | undefined;
  readonly identity: ConfigIdentity | undefined;
  readonly deploymentId: string | undefined;
}

/**
 * Prepare the body actually sent upstream. Every invalid or disabled state returns
 * the original bytes; observe-only is the default, not a policy convention.
 */
export async function prepareRequestBody(args: {
  provider: Provider;
  originalBody: string | undefined;
  runId: string;
  callSiteId: string | undefined;
  bypass: boolean;
  enforcementEnabled: boolean;
  policyRaw: string | undefined;
}): Promise<PreparedRequest> {
  const originalIdentity = await configIdentity(args.provider, args.originalBody);
  const unchanged: PreparedRequest = {
    body: args.originalBody,
    identity: originalIdentity,
    deploymentId: undefined,
  };
  if (
    !args.enforcementEnabled ||
    args.bypass ||
    !args.originalBody ||
    !args.callSiteId ||
    !originalIdentity
  ) {
    return unchanged;
  }
  const policy = parseDeploymentPolicy(args.policyRaw);
  if (
    !policy ||
    policy.provider !== args.provider ||
    policy.callSiteId !== args.callSiteId ||
    policy.sourceConfigId !== originalIdentity.configId ||
    !(await isInRollout(policy.id, args.runId, policy.rolloutPercent))
  ) {
    return unchanged;
  }
  const body = applyBoundedPatch(args.provider, args.originalBody, policy.patch);
  if (!body) return unchanged;
  const identity = await configIdentity(args.provider, body);
  if (!identity) return unchanged;
  return { body, identity, deploymentId: policy.id };
}

type JsonObject = Record<string, unknown>;

/**
 * Hash the request-local configuration the gateway can prove from one request.
 *
 * Conversation messages are deliberately excluded from the system hash. This is a
 * raw system-content identity, not the learned template identity described by the
 * optimizer design; learning slots across requests belongs in a stateful layer.
 */
export async function configIdentity(
  provider: Provider,
  requestBody: string | undefined,
): Promise<ConfigIdentity | undefined> {
  const body = parseObject(requestBody);
  if (!body) return undefined;

  const system = withoutCacheFields(systemConfiguration(provider, body));
  const tools = withoutCacheFields(body["tools"] ?? body["functions"] ?? []);
  const params = parameterConfiguration(provider, body);
  const [systemHash, toolsHash, paramsHash] = await Promise.all([
    hashCanonical(system),
    hashCanonical(tools),
    hashCanonical(params),
  ]);
  const configId = await hashCanonical({ systemHash, toolsHash, paramsHash });
  return { systemHash, toolsHash, paramsHash, configId };
}

/** Apply only the three request-body levers authorized for the first gateway slice. */
export function applyBoundedPatch(
  provider: Provider,
  requestBody: string,
  patch: BoundedConfigPatch,
): string | undefined {
  const body = parseObject(requestBody);
  if (!body || !validPatch(patch)) return undefined;

  // Gemini selects its model in the URL, not the JSON body. Adding a dead body
  // field would stamp a model that was never served, so the body-only slice refuses.
  if (provider === "gemini" && patch.model !== undefined) return undefined;
  if (patch.model !== undefined) body["model"] = patch.model;
  if (provider === "openai" || provider === "openrouter") {
    applyOpenAiPatch(body, patch);
  } else if (provider === "anthropic") {
    applyAnthropicPatch(body, patch);
  } else {
    applyGeminiPatch(body, patch);
  }
  return JSON.stringify(body);
}

/** Stable run-level ramp assignment. Raising a ramp never removes an enrolled run. */
export async function isInRollout(
  deploymentId: string,
  runId: string,
  percent: RolloutPercent,
): Promise<boolean> {
  if (percent === 100) return true;
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(`${deploymentId}:${runId}`),
  );
  const bucket = new DataView(digest).getUint32(0) % 10_000;
  return bucket < percent * 100;
}

/** Parse an env-delivered policy strictly; malformed control-plane state is inert. */
export function parseDeploymentPolicy(raw: string | undefined): DeploymentPolicy | undefined {
  const value = parseObject(raw);
  if (!value) return undefined;
  if (!hasOnlyKeys(value, ["id", "provider", "callSiteId", "sourceConfigId", "rolloutPercent", "patch"])) {
    return undefined;
  }
  const { id, provider, callSiteId, sourceConfigId, rolloutPercent, patch } = value;
  if (typeof id !== "string" || id.trim() === "") return undefined;
  if (!isProvider(provider)) return undefined;
  if (typeof callSiteId !== "string" || callSiteId.trim() === "") return undefined;
  if (typeof sourceConfigId !== "string" || sourceConfigId === "") return undefined;
  if (!isRolloutPercent(rolloutPercent)) return undefined;
  if (!isObject(patch) || !hasOnlyKeys(patch, ["model", "reasoningEffort", "maxTokens"])) {
    return undefined;
  }
  if (!validPatch(patch)) return undefined;
  return { id, provider, callSiteId, sourceConfigId, rolloutPercent, patch };
}

function systemConfiguration(provider: Provider, body: JsonObject): unknown {
  if (provider === "anthropic") return body["system"] ?? null;
  if (provider === "gemini") {
    return body["systemInstruction"] ?? body["system_instruction"] ?? null;
  }
  const messages = body["messages"];
  if (!Array.isArray(messages)) return null;
  return messages.filter(
    (message): message is JsonObject =>
      isObject(message) && (message["role"] === "system" || message["role"] === "developer"),
  );
}

function parameterConfiguration(provider: Provider, body: JsonObject): JsonObject {
  if (provider === "anthropic") {
    return {
      provider,
      ...pick(body, ["model", "thinking", "output_config", "max_tokens"]),
      cache: cacheConfiguration(body),
    };
  }
  if (provider === "gemini") {
    return {
      provider,
      ...pick(body, ["model", "cachedContent", "cached_content"]),
      generationConfig: pickObject(body["generationConfig"] ?? body["generation_config"], [
        "thinkingConfig",
        "thinking_config",
        "maxOutputTokens",
        "max_output_tokens",
      ]),
      cache: cacheConfiguration(body),
    };
  }
  return {
    provider,
    ...pick(body, [
      "model",
      "reasoning_effort",
      "reasoning",
      "max_tokens",
      "max_completion_tokens",
      "prompt_cache_key",
      "service_tier",
    ]),
    cache: cacheConfiguration(body),
  };
}

const CACHE_FIELDS = new Set([
  "cache_control",
  "cacheControl",
  "cached_content",
  "cachedContent",
  "prompt_cache_key",
]);

function withoutCacheFields(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(withoutCacheFields);
  if (!isObject(value)) return value;
  const out: JsonObject = {};
  for (const [key, nested] of Object.entries(value)) {
    if (!CACHE_FIELDS.has(key)) out[key] = withoutCacheFields(nested);
  }
  return out;
}

/** Cache markers live inside provider-specific message/tool shapes; retain paths. */
function cacheConfiguration(value: unknown): readonly JsonObject[] {
  const found: JsonObject[] = [];
  collectCacheFields(value, "$", found);
  return found;
}

function collectCacheFields(value: unknown, path: string, found: JsonObject[]): void {
  if (Array.isArray(value)) {
    value.forEach((nested, index) => collectCacheFields(nested, `${path}/${index}`, found));
    return;
  }
  if (!isObject(value)) return;
  for (const key of Object.keys(value).sort()) {
    const nested = value[key];
    if (CACHE_FIELDS.has(key)) found.push({ path: `${path}/${key}`, value: nested });
    else collectCacheFields(nested, `${path}/${key}`, found);
  }
}

function applyOpenAiPatch(body: JsonObject, patch: BoundedConfigPatch): void {
  if (patch.reasoningEffort !== undefined) {
    const reasoning = body["reasoning"];
    if (isObject(reasoning)) reasoning["effort"] = patch.reasoningEffort;
    else body["reasoning_effort"] = patch.reasoningEffort;
  }
  if (patch.maxTokens !== undefined) {
    const key = Object.hasOwn(body, "max_completion_tokens")
      ? "max_completion_tokens"
      : "max_tokens";
    body[key] = patch.maxTokens;
  }
}

function applyAnthropicPatch(body: JsonObject, patch: BoundedConfigPatch): void {
  if (patch.reasoningEffort !== undefined) {
    const output = isObject(body["output_config"]) ? body["output_config"] : {};
    output["effort"] = patch.reasoningEffort;
    body["output_config"] = output;
  }
  if (patch.maxTokens !== undefined) body["max_tokens"] = patch.maxTokens;
}

function applyGeminiPatch(body: JsonObject, patch: BoundedConfigPatch): void {
  const generation = isObject(body["generationConfig"]) ? body["generationConfig"] : {};
  if (patch.reasoningEffort !== undefined) {
    const thinking = isObject(generation["thinkingConfig"])
      ? generation["thinkingConfig"]
      : {};
    thinking["thinkingLevel"] = patch.reasoningEffort;
    generation["thinkingConfig"] = thinking;
  }
  if (patch.maxTokens !== undefined) generation["maxOutputTokens"] = patch.maxTokens;
  if (Object.keys(generation).length > 0) body["generationConfig"] = generation;
}

function validPatch(value: JsonObject | BoundedConfigPatch): value is BoundedConfigPatch {
  const model = value.model;
  const reasoning = value.reasoningEffort;
  const maxTokens = value.maxTokens;
  if (model !== undefined && (typeof model !== "string" || model.trim() === "")) return false;
  if (
    reasoning !== undefined &&
    (typeof reasoning !== "string" || reasoning.trim() === "")
  ) return false;
  if (
    maxTokens !== undefined &&
    (typeof maxTokens !== "number" || !Number.isSafeInteger(maxTokens) || maxTokens <= 0)
  ) return false;
  return model !== undefined || reasoning !== undefined || maxTokens !== undefined;
}

function parseObject(raw: string | undefined): JsonObject | undefined {
  if (!raw) return undefined;
  try {
    const value: unknown = JSON.parse(raw);
    return isObject(value) ? value : undefined;
  } catch {
    return undefined;
  }
}

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function pick(value: JsonObject, keys: readonly string[]): JsonObject {
  const out: JsonObject = {};
  for (const key of keys) {
    if (Object.hasOwn(value, key)) out[key] = value[key];
  }
  return out;
}

function pickObject(value: unknown, keys: readonly string[]): JsonObject {
  return isObject(value) ? pick(value, keys) : {};
}

function hasOnlyKeys(value: JsonObject, allowed: readonly string[]): boolean {
  const allowedSet = new Set(allowed);
  return Object.keys(value).every((key) => allowedSet.has(key));
}

function isProvider(value: unknown): value is Provider {
  return value === "openai" || value === "anthropic" || value === "gemini" || value === "openrouter";
}

function isRolloutPercent(value: unknown): value is RolloutPercent {
  return value === 1 || value === 5 || value === 25 || value === 100;
}

async function hashCanonical(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalJson(value));
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const object = value as JsonObject;
  return `{${Object.keys(object)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(object[key])}`)
    .join(",")}}`;
}

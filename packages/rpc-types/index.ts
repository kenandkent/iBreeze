export interface HealthComponents {
  rpc: "up" | "down";
  [key: string]: string;
}

export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  components: HealthComponents;
}

export interface RpcRequest {
  type: "request";
  id: string;
  method: string;
  params: Record<string, unknown>;
}

export interface RpcResponse {
  type: "response";
  id: string;
  result: unknown | null;
  error: string | null;
}

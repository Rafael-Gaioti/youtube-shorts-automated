const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ServerStatus {
  status: string;
  timestamp: string;
  platform: string;
  active_jobs_count: number;
  active_jobs: Record<string, unknown>;
  supabase_connection: boolean;
}

export interface JobResponse {
  status: string;
  video_code: string;
  message: string;
}

export async function getServerStatus(): Promise<ServerStatus> {
  const res = await fetch(`${API_URL}/`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Server error: ${res.status}`);
  return res.json();
}

export async function startPipelineJob(
  youtubeUrl: string,
  profile = "recommended"
): Promise<JobResponse> {
  const res = await fetch(`${API_URL}/api/process`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: youtubeUrl,
      profile,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail || `Server error: ${res.status}`);
  }
  return res.json();
}

export async function getActiveTasks() {
  const res = await fetch(`${API_URL}/api/active-tasks`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Error: ${res.status}`);
  return res.json();
}

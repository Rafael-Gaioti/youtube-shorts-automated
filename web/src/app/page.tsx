"use client";

import { useEffect, useState, useCallback } from "react";
import { supabase } from "@/lib/supabase";
import { getServerStatus, startPipelineJob, type ServerStatus } from "@/lib/api";
import {
  Activity,
  Video,
  Scissors,
  Type,
  CheckCircle2,
  Clock,
  Cpu,
  Play,
  Loader2,
  Wifi,
  WifiOff,
  Send,
  X,
  AlertTriangle,
} from "lucide-react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// Shadcn UI Components
import {
  Card,
  CardHeader,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type VideoRecord = {
  id: string;
  video_code: string;
  title: string;
  stage: string;
  updated_at: string;
};

const STAGE_CONFIG: Record<
  string,
  { icon: React.ElementType; color: string; label: string }
> = {
  discovered: { icon: Clock, color: "text-gray-400", label: "Descoberto" },
  downloading: {
    icon: Video,
    color: "text-blue-300 animate-pulse",
    label: "Baixando...",
  },
  downloaded: { icon: Video, color: "text-blue-400", label: "Download" },
  transcribing: {
    icon: Type,
    color: "text-purple-300 animate-pulse",
    label: "Transcrevendo...",
  },
  transcribed: { icon: Type, color: "text-purple-400", label: "Transcrito" },
  analyzing: {
    icon: Scissors,
    color: "text-yellow-300 animate-pulse",
    label: "Analisando...",
  },
  analyzed: { icon: Scissors, color: "text-yellow-400", label: "Analisado" },
  cutting: {
    icon: Scissors,
    color: "text-orange-300 animate-pulse",
    label: "Cortando...",
  },
  exported: { icon: CheckCircle2, color: "text-emerald-400", label: "Pronto" },
  uploading: {
    icon: Activity,
    color: "text-cyan-300 animate-pulse",
    label: "Subindo...",
  },
  uploaded: { icon: Activity, color: "text-cyan-400", label: "No YouTube" },
  failed: { icon: AlertTriangle, color: "text-red-400", label: "Erro" },
};

const STAGE_PROGRESS: Record<string, number> = {
  discovered: 10,
  downloading: 20,
  downloaded: 30,
  transcribing: 40,
  transcribed: 55,
  analyzing: 65,
  analyzed: 75,
  cutting: 85,
  exported: 95,
  uploading: 97,
  uploaded: 100,
  failed: 100,
};

export default function OperationalDashboard() {
  const [videos, setVideos] = useState<VideoRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [serverStatus, setServerStatus] = useState<ServerStatus | null>(null);
  const [serverOnline, setServerOnline] = useState(false);
  const [showNewJob, setShowNewJob] = useState(false);
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  // Poll server status every 15s
  const fetchStatus = useCallback(async () => {
    try {
      const status = await getServerStatus();
      setServerStatus(status);
      setServerOnline(true);
    } catch {
      setServerOnline(false);
      setServerStatus(null);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  useEffect(() => {
    async function fetchVideos() {
      const { data, error } = await supabase
        .from("videos")
        .select("*")
        .order("updated_at", { ascending: false })
        .limit(20);

      if (!error && data) {
        setVideos(data);
      }
      setLoading(false);
    }

    fetchVideos();

    // Realtime subscription
    const channel = supabase
      .channel("schema-db-changes")
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "videos",
        },
        (payload) => {
          if (payload.eventType === "INSERT") {
            setVideos((prev) =>
              [payload.new as VideoRecord, ...prev].slice(0, 20),
            );
          } else if (payload.eventType === "UPDATE") {
            setVideos((prev) =>
              prev.map((v) =>
                v.video_code === payload.new.video_code
                  ? (payload.new as VideoRecord)
                  : v,
              ),
            );
          }
        },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  const handleStartJob = async () => {
    if (!youtubeUrl.trim()) return;
    setSubmitting(true);
    setSubmitError("");
    try {
      await startPipelineJob(youtubeUrl.trim());
      setYoutubeUrl("");
      setShowNewJob(false);
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : "Erro ao iniciar pipeline");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="min-h-screen p-8 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-white mb-2">
            Shorts Automated
          </h1>
          <p className="text-gray-400 flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span
                className={cn(
                  "animate-ping absolute inline-flex h-full w-full rounded-full opacity-75",
                  serverOnline ? "bg-emerald-400" : "bg-red-400"
                )}
              />
              <span
                className={cn(
                  "relative inline-flex rounded-full h-2 w-2",
                  serverOnline ? "bg-emerald-500" : "bg-red-500"
                )}
              />
            </span>
            Monitor Operacional em Tempo Real
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Start Job Button */}
          <button
            onClick={() => setShowNewJob(!showNewJob)}
            className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-semibold text-sm flex items-center gap-2 transition-all duration-300 hover:scale-105 active:scale-95 shadow-lg shadow-indigo-500/20"
          >
            <Play className="w-4 h-4" />
            Novo Job
          </button>

          {/* Server Status Card */}
          <div className="p-4 glass-card rounded-2xl flex items-center gap-4">
            <div
              className={cn(
                "p-2 rounded-lg",
                serverOnline ? "bg-emerald-500/10" : "bg-red-500/10"
              )}
            >
              {serverOnline ? (
                <Wifi className="w-6 h-6 text-emerald-500" />
              ) : (
                <WifiOff className="w-6 h-6 text-red-500" />
              )}
            </div>
            <div>
              <div className="text-xs text-gray-400 uppercase font-bold tracking-wider">
                VPS Backend
              </div>
              <div
                className={cn(
                  "text-lg font-mono",
                  serverOnline ? "text-emerald-400" : "text-red-400"
                )}
              >
                {serverOnline
                  ? `ONLINE · ${serverStatus?.active_jobs_count ?? 0} jobs`
                  : "OFFLINE"}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* New Job Form */}
      {showNewJob && (
        <div className="glass-card rounded-2xl p-6 border border-indigo-500/20 animate-in fade-in slide-in-from-top-2 duration-300">
          <div className="flex items-center gap-3 mb-4">
            <Cpu className="w-5 h-5 text-indigo-400" />
            <h3 className="text-white font-semibold text-lg">Iniciar Pipeline</h3>
            <button
              onClick={() => setShowNewJob(false)}
              className="ml-auto text-gray-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <div className="flex gap-3">
            <input
              type="text"
              value={youtubeUrl}
              onChange={(e) => setYoutubeUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleStartJob()}
              placeholder="Cole a URL do YouTube aqui..."
              className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/30 transition-all font-mono text-sm"
              disabled={submitting || !serverOnline}
            />
            <button
              onClick={handleStartJob}
              disabled={submitting || !youtubeUrl.trim() || !serverOnline}
              className="px-6 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-xl font-semibold text-sm flex items-center gap-2 transition-all duration-300 shadow-lg shadow-indigo-500/20"
            >
              {submitting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
              {submitting ? "Processando..." : "Iniciar"}
            </button>
          </div>
          {submitError && (
            <p className="mt-3 text-red-400 text-sm flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" />
              {submitError}
            </p>
          )}
          {!serverOnline && (
            <p className="mt-3 text-yellow-400 text-sm flex items-center gap-2">
              <WifiOff className="w-4 h-4" />
              Backend offline — não é possível iniciar jobs.
            </p>
          )}
        </div>
      )}

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {loading ? (
          <div className="col-span-full text-center py-20 text-gray-500">
            <Loader2 className="w-8 h-8 animate-spin mx-auto mb-4" />
            Carregando pipeline...
          </div>
        ) : videos.length === 0 ? (
          <div className="col-span-full text-center py-20 text-gray-500">
            <Video className="w-12 h-12 mx-auto mb-4 opacity-30" />
            <p className="text-lg mb-2">Nenhum vídeo em processamento.</p>
            <p className="text-sm">
              Clique em{" "}
              <span className="text-indigo-400 font-semibold">Novo Job</span>{" "}
              para começar.
            </p>
          </div>
        ) : (
          videos
            .filter((v) => !!STAGE_CONFIG[v.stage])
            .map((video) => {
              const config = STAGE_CONFIG[video.stage];
              const Icon = config.icon;

              return (
                <Card
                  key={video.video_code}
                  className="glass-card border-white/5 bg-white/5 backdrop-blur-xl overflow-hidden group hover:border-white/20 transition-all duration-500"
                >
                  <CardHeader className="p-6 pb-4">
                    <div className="flex justify-between items-start">
                      <div
                        className={cn(
                          "p-3 rounded-2xl bg-white/5 transition-transform group-hover:scale-110 duration-500",
                          config.color,
                        )}
                      >
                        <Icon className="w-6 h-6" />
                      </div>
                      <Badge
                        variant="secondary"
                        className={cn(
                          "bg-white/5 border-white/10 hover:bg-white/10 transition-colors uppercase text-[10px] font-bold tracking-widest",
                          config.color,
                        )}
                      >
                        {config.label}
                      </Badge>
                    </div>
                  </CardHeader>

                  <CardContent className="space-y-6">
                    {/* Progress Area */}
                    <div className="space-y-3">
                      <div className="flex justify-between items-center text-[10px] text-gray-500 font-bold uppercase tracking-tighter">
                        <span>Pipeline Progress</span>
                        <span>{STAGE_PROGRESS[video.stage] || 0}%</span>
                      </div>
                      <Progress
                        value={STAGE_PROGRESS[video.stage] || 0}
                        className="h-1 bg-white/5"
                      />
                    </div>

                    <div>
                      <h3 className="font-semibold text-white line-clamp-2 min-h-[3rem] text-sm leading-relaxed group-hover:text-indigo-300 transition-colors">
                        {video.title || video.video_code}
                      </h3>
                      <p className="text-[10px] text-gray-500 mt-2 font-mono flex items-center gap-1 opacity-70">
                        <span className="w-1 h-1 rounded-full bg-gray-500" />
                        REF: {video.video_code}
                      </p>
                    </div>
                  </CardContent>

                  <CardFooter className="p-6 pt-4 border-t border-white/5 flex justify-between items-center bg-white/[0.02]">
                    <span className="flex items-center gap-1.5 text-[10px] text-gray-500 font-medium">
                      <Clock className="w-3.5 h-3.5" />
                      {new Date(video.updated_at).toLocaleTimeString()}
                    </span>
                    <button className="text-[10px] font-bold uppercase tracking-widest text-gray-400 hover:text-white transition-all flex items-center gap-1 group/btn">
                      Details
                      <Activity className="w-3 h-3 group-hover/btn:animate-pulse" />
                    </button>
                  </CardFooter>
                </Card>
              );
            })
        )}
      </div>
    </main>
  );
}

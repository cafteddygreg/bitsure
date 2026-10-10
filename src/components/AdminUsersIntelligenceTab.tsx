import React, { useState, useEffect, useMemo } from "react";
import {
  Users,
  Search,
  RefreshCw,
  Download,
  Shield,
  Globe,
  Cpu,
  Smartphone,
  Monitor,
  Tablet,
  Lock,
  Unlock,
  CheckCircle2,
  AlertTriangle,
  Activity,
  DollarSign,
  Eye,
  EyeOff,
  FileText,
  Key,
  Clock,
  MapPin,
  Server,
  ChevronRight,
  Bell,
  MessageSquare,
} from "lucide-react";

interface AdminUsersIntelligenceTabProps {
  apiFetch: (path: string, options?: RequestInit) => Promise<any>;
  onAdminUserAction?: (action: string, targetUserId: number, extra?: Record<string, any>) => Promise<void>;
  onOpenTermsPage?: () => void;
}

export function AdminUsersIntelligenceTab({
  apiFetch,
  onAdminUserAction,
  onOpenTermsPage,
}: AdminUsersIntelligenceTabProps) {
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const [data, setData] = useState<any>(null);
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [filterMode, setFilterMode] = useState<string>("all");
  const [revealSensitive, setRevealSensitive] = useState<boolean>(false);
  const [activeSubTab, setActiveSubTab] = useState<
    "identity" | "device" | "sensitive" | "trading" | "activity"
  >("identity");
  const [actionBusy, setActionBusy] = useState<boolean>(false);

  const loadIntelligence = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await apiFetch("/api/admin/users-intelligence");
      if (res && res.ok) {
        setData(res);
        if (res.users && res.users.length > 0 && selectedUserId === null) {
          setSelectedUserId(res.users[0].user_id);
        }
      } else {
        setError(res?.error || "Impossible de charger les dossiers utilisateurs.");
      }
    } catch (e: any) {
      setError(e?.message || "Erreur réseau lors du chargement des dossiers utilisateurs.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadIntelligence();
  }, []);

  const users: any[] = data?.users || [];
  const summary = data?.summary || {};

  const filteredUsers = useMemo(() => {
    return users.filter((u) => {
      const q = searchQuery.trim().toLowerCase();
      if (q) {
        const hay = [
          String(u.user_id || ""),
          u.identity?.email || "",
          u.identity?.display_name || "",
          u.identity?.username || "",
          u.identity?.telegram_handle || "",
          u.network_location?.ip_address || "",
          u.network_location?.country || "",
          u.network_location?.city || "",
          u.device?.os_name || "",
          u.device?.browser_name || "",
          u.device?.device_vendor_model || "",
        ]
          .join(" ")
          .toLowerCase();
        if (!hay.includes(q)) return false;
      }

      if (filterMode === "pending") return u.identity?.account_status === "PENDING_APPROVAL";
      if (filterMode === "approved") return u.identity?.account_status === "APPROVED";
      if (filterMode === "pro_vip") return ["pro", "vip"].includes(u.subscription?.plan);
      if (filterMode === "binance") return Boolean(u.sensitive_security?.binance_credentials?.configured);
      if (filterMode === "consented") return Boolean(u.consent?.terms_accepted);
      if (filterMode === "gps") return u.network_location?.latitude != null;
      return true;
    });
  }, [users, searchQuery, filterMode]);

  const selectedUser = useMemo(() => {
    if (!filteredUsers.length) return null;
    return filteredUsers.find((u) => u.user_id === selectedUserId) || filteredUsers[0];
  }, [filteredUsers, selectedUserId]);

  const formatTs = (ts: number | null | undefined) => {
    if (!ts || ts <= 0) return "Jamais / N/A";
    try {
      return new Date(ts * 1000).toLocaleString("fr-FR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return String(ts);
    }
  };

  const handleExportJson = () => {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `bitsure_users_intelligence_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleQuickAction = async (action: string, targetUid: number, extra: Record<string, any> = {}) => {
    if (!onAdminUserAction) return;
    setActionBusy(true);
    try {
      await onAdminUserAction(action, targetUid, extra);
      await loadIntelligence();
    } finally {
      setActionBusy(false);
    }
  };

  const renderDeviceIcon = (type: string) => {
    const t = (type || "").toLowerCase();
    if (t.includes("mobile")) return <Smartphone className="w-4 h-4 text-sky-400" />;
    if (t.includes("tablet")) return <Tablet className="w-4 h-4 text-purple-400" />;
    return <Monitor className="w-4 h-4 text-emerald-400" />;
  };

  return (
    <div className="space-y-5">
      {/* Top Executive Telemetry Header */}
      <div className="rounded-xl border border-amber-500/30 bg-[#0B101D] p-5 shadow-lg">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-amber-500/15 border border-amber-500/30 flex items-center justify-center">
              <Users className="w-5 h-5 text-amber-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-white tracking-tight">
                  Dossiers Utilisateurs 360° &amp; Télémétrie (Admin Seulement)
                </h2>
                <span className="px-2 py-0.5 text-[10px] font-mono font-semibold uppercase rounded bg-rose-500/15 text-rose-300 border border-rose-500/30">
                  Accès Restreint Admin
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Vue intégrale par utilisateur : Identité, Consentement CGU, Adresse IP, Localisation GPS/Réseau,
                Appareil, Données Sensibles (Clés API, PIN, Sessions) et Activité Trading.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {onOpenTermsPage && (
              <button
                onClick={onOpenTermsPage}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-semibold transition"
              >
                <FileText className="w-3.5 h-3.5 text-amber-400" />
                Voir l&apos;onglet public CGU (v{summary.terms_current_version || "2.2.0"})
              </button>
            )}
            <button
              onClick={() => setRevealSensitive((prev) => !prev)}
              className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border text-xs font-semibold transition ${
                revealSensitive
                  ? "bg-rose-500/20 border-rose-500/50 text-rose-200"
                  : "bg-slate-900 hover:bg-slate-800 border-slate-700 text-slate-300"
              }`}
            >
              {revealSensitive ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
              {revealSensitive ? "Masquer les données sensibles" : "Afficher les données sensibles"}
            </button>
            <button
              onClick={handleExportJson}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-semibold transition"
            >
              <Download className="w-3.5 h-3.5 text-sky-400" />
              Exporter JSON
            </button>
            <button
              onClick={loadIntelligence}
              disabled={loading}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold transition disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              Actualiser
            </button>
          </div>
        </div>

        {/* Summary KPI Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2.5 mt-4">
          <div className="p-3 rounded-lg bg-slate-950/90 border border-slate-800/80">
            <div className="text-[10px] font-mono uppercase text-slate-400">Total Utilisateurs</div>
            <div className="text-lg font-bold font-mono text-white mt-0.5">{summary.total_users ?? 0}</div>
          </div>
          <div className="p-3 rounded-lg bg-slate-950/90 border border-slate-800/80">
            <div className="text-[10px] font-mono uppercase text-emerald-400">CGU Acceptées</div>
            <div className="text-lg font-bold font-mono text-emerald-400 mt-0.5">{summary.consented_users ?? 0}</div>
          </div>
          <div className="p-3 rounded-lg bg-slate-950/90 border border-slate-800/80">
            <div className="text-[10px] font-mono uppercase text-amber-400">En attente</div>
            <div className="text-lg font-bold font-mono text-amber-400 mt-0.5">{summary.pending_users ?? 0}</div>
          </div>
          <div className="p-3 rounded-lg bg-slate-950/90 border border-slate-800/80">
            <div className="text-[10px] font-mono uppercase text-sky-400">Approuvés</div>
            <div className="text-lg font-bold font-mono text-sky-400 mt-0.5">{summary.approved_users ?? 0}</div>
          </div>
          <div className="p-3 rounded-lg bg-slate-950/90 border border-slate-800/80">
            <div className="text-[10px] font-mono uppercase text-purple-400">Comptes PRO / VIP</div>
            <div className="text-lg font-bold font-mono text-purple-400 mt-0.5">{summary.pro_or_vip_users ?? 0}</div>
          </div>
          <div className="p-3 rounded-lg bg-slate-950/90 border border-slate-800/80">
            <div className="text-[10px] font-mono uppercase text-cyan-400">Télémétrie Appareil</div>
            <div className="text-lg font-bold font-mono text-cyan-400 mt-0.5">{summary.with_telemetry ?? 0}</div>
          </div>
          <div className="p-3 rounded-lg bg-slate-950/90 border border-slate-800/80">
            <div className="text-[10px] font-mono uppercase text-teal-400">GPS Précis Autorisé</div>
            <div className="text-lg font-bold font-mono text-teal-400 mt-0.5">{summary.with_geolocation_coords ?? 0}</div>
          </div>
          <div className="p-3 rounded-lg bg-slate-950/90 border border-slate-800/80">
            <div className="text-[10px] font-mono uppercase text-rose-400">Clés Binance Liées</div>
            <div className="text-lg font-bold font-mono text-rose-400 mt-0.5">{summary.with_binance_keys ?? 0}</div>
          </div>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Search & Filter Controls */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Rechercher par email, User ID, @telegram, adresse IP, pays, ville, OS, modèle d'appareil..."
            className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-[#0B101D] border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500/50"
          />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {[
            { id: "all", label: "Tous" },
            { id: "consented", label: "CGU Acceptées" },
            { id: "pending", label: "En attente" },
            { id: "approved", label: "Approuvés" },
            { id: "pro_vip", label: "PRO / VIP" },
            { id: "binance", label: "API Binance" },
            { id: "gps", label: "GPS Actif" },
          ].map((f) => (
            <button
              key={f.id}
              onClick={() => setFilterMode(f.id)}
              className={`px-3 py-2 rounded-lg text-xs font-semibold border transition ${
                filterMode === f.id
                  ? "bg-amber-500/20 border-amber-500/40 text-amber-300"
                  : "bg-[#0B101D] border-slate-800 text-slate-400 hover:text-slate-200"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Main Master-Detail Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Left List of Users (4 cols) */}
        <div className="lg:col-span-4 rounded-xl border border-slate-800/90 bg-[#0B101D] overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
            <span className="text-xs font-bold text-slate-200 uppercase tracking-wider font-mono">
              Comptes répertoriés ({filteredUsers.length})
            </span>
          </div>
          <div className="max-h-[720px] overflow-y-auto divide-y divide-slate-800/70">
            {filteredUsers.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-500">
                Aucun utilisateur ne correspond aux critères.
              </div>
            ) : (
              filteredUsers.map((u) => {
                const isSelected = selectedUser && selectedUser.user_id === u.user_id;
                const status = u.identity?.account_status || "PENDING_APPROVAL";
                const ip = u.network_location?.ip_address || "IP non relevée";
                const devType = u.device?.device_type || "Inconnu";
                return (
                  <button
                    key={u.user_id}
                    onClick={() => setSelectedUserId(u.user_id)}
                    className={`w-full text-left p-3.5 transition flex items-start justify-between gap-2 ${
                      isSelected ? "bg-amber-500/10 border-l-2 border-l-amber-400" : "hover:bg-slate-900/60"
                    }`}
                  >
                    <div className="space-y-1 min-w-0">
                      <div className="flex items-center gap-2">
                        {renderDeviceIcon(devType)}
                        <span className="text-xs font-bold text-white truncate">
                          {u.identity?.display_name || u.identity?.username || `UID #${u.user_id}`}
                        </span>
                        <span className="text-[10px] font-mono text-slate-400">#{u.user_id}</span>
                      </div>
                      <div className="text-[11px] text-slate-400 truncate">
                        {u.identity?.email || "Compte Telegram uniquement"}
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5 pt-1">
                        <span
                          className={`px-1.5 py-0.5 text-[9px] font-mono font-semibold uppercase rounded ${
                            status === "APPROVED"
                              ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                              : status === "PENDING_APPROVAL"
                              ? "bg-amber-500/15 text-amber-300 border border-amber-500/30"
                              : "bg-rose-500/15 text-rose-300 border border-rose-500/30"
                          }`}
                        >
                          {status}
                        </span>
                        <span className="px-1.5 py-0.5 text-[9px] font-mono uppercase rounded bg-slate-800 text-slate-300">
                          {u.subscription?.plan || "free"}
                        </span>
                        <span
                          className={`px-1.5 py-0.5 text-[9px] font-mono rounded ${
                            u.consent?.terms_accepted
                              ? "bg-sky-500/15 text-sky-300 border border-sky-500/30"
                              : "bg-slate-800 text-slate-400"
                          }`}
                        >
                          {u.consent?.terms_accepted ? `CGU v${u.consent.terms_version}` : "CGU non signées"}
                        </span>
                      </div>
                      <div className="text-[10px] font-mono text-slate-500 truncate pt-0.5">
                        IP: {ip} • {u.device?.os_name || "OS ?"} / {u.device?.browser_name || "Nav ?"}
                      </div>
                    </div>
                    <ChevronRight className="w-4 h-4 text-slate-500 shrink-0 mt-1" />
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Right 360° User Dossier (8 cols) */}
        <div className="lg:col-span-8 space-y-4">
          {!selectedUser ? (
            <div className="rounded-xl border border-slate-800 bg-[#0B101D] p-8 text-center text-xs text-slate-400">
              Sélectionnez un utilisateur dans la liste de gauche pour inspecter son dossier 360° complet.
            </div>
          ) : (
            <div className="rounded-xl border border-slate-800/90 bg-[#0B101D] p-5 space-y-5">
              {/* User Dossier Header */}
              <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-800 pb-4">
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-lg font-bold text-white">
                      {selectedUser.identity?.display_name || selectedUser.identity?.username}
                    </span>
                    <span className="px-2 py-0.5 rounded bg-slate-800 text-amber-300 font-mono text-xs font-semibold">
                      UID: {selectedUser.user_id}
                    </span>
                    <span className="px-2 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30 font-mono text-xs uppercase font-semibold">
                      Rôle: {selectedUser.identity?.role}
                    </span>
                    <span className="px-2 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30 font-mono text-xs uppercase font-semibold">
                      Plan: {selectedUser.subscription?.plan}
                    </span>
                  </div>
                  <div className="text-xs text-slate-400 flex flex-wrap items-center gap-3">
                    <span>Email: <strong className="text-slate-200">{selectedUser.identity?.email || "Non renseigné"}</strong></span>
                    <span>•</span>
                    <span>Telegram: <strong className="text-slate-200">{selectedUser.identity?.telegram_handle || "N/A"}</strong></span>
                    <span>•</span>
                    <span>Dernière activité: <strong className="text-slate-200">{formatTs(selectedUser.identity?.last_seen_at)}</strong></span>
                  </div>
                </div>

                {/* Quick Admin Actions */}
                {onAdminUserAction && (
                  <div className="flex flex-wrap items-center gap-2">
                    {selectedUser.identity?.account_status !== "APPROVED" && (
                      <button
                        disabled={actionBusy}
                        onClick={() => handleQuickAction("approve", selectedUser.user_id, { role: "tester" })}
                        className="px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs transition"
                      >
                        Approuver le compte
                      </button>
                    )}
                    {selectedUser.identity?.account_status === "APPROVED" && (
                      <button
                        disabled={actionBusy}
                        onClick={() => handleQuickAction("suspend", selectedUser.user_id)}
                        className="px-3 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/40 text-rose-300 font-semibold text-xs transition"
                      >
                        Suspendre
                      </button>
                    )}
                    <button
                      disabled={actionBusy}
                      onClick={() => handleQuickAction("set_plan", selectedUser.user_id, { plan: "pro", days: 30 })}
                      className="px-3 py-1.5 rounded-lg bg-sky-500/20 hover:bg-sky-500/30 border border-sky-500/40 text-sky-300 font-semibold text-xs transition"
                    >
                      Activer PRO (30j)
                    </button>
                    <button
                      disabled={actionBusy}
                      onClick={() => handleQuickAction("set_plan", selectedUser.user_id, { plan: "vip", days: 30 })}
                      className="px-3 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-300 font-semibold text-xs transition"
                    >
                      Activer VIP (30j)
                    </button>
                  </div>
                )}
              </div>

              {/* Sub-navigation inside the User Dossier */}
              <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 pb-3">
                {[
                  { id: "identity", label: "1. Identité, Consentement CGU & Abonnement", icon: Shield },
                  { id: "device", label: "2. Appareil, OS, Adresse IP & Localisation GPS", icon: Globe },
                  { id: "sensitive", label: "3. Données Sensibles (Clés API, PIN, Sessions)", icon: Lock },
                  { id: "trading", label: "4. Portefeuilles Paper & Live Binance", icon: DollarSign },
                  { id: "activity", label: "5. Historique Signaux, Alertes & Sécurité", icon: Activity },
                ].map((tab) => {
                  const Icon = tab.icon;
                  return (
                    <button
                      key={tab.id}
                      onClick={() => setActiveSubTab(tab.id as any)}
                      className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border transition ${
                        activeSubTab === tab.id
                          ? "bg-amber-500/20 border-amber-500/40 text-amber-300"
                          : "bg-slate-900/80 border-slate-800 text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      <Icon className="w-3.5 h-3.5" />
                      {tab.label}
                    </button>
                  );
                })}
              </div>

              {/* SUB-TAB 1: IDENTITY, CONSENT & SUBSCRIPTION */}
              {activeSubTab === "identity" && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Personal Identity */}
                  <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2.5">
                    <div className="text-xs font-bold text-amber-400 uppercase font-mono flex items-center gap-2">
                      <Users className="w-4 h-4" /> Informations Personnelles &amp; Identité
                    </div>
                    <div className="space-y-1.5 text-xs">
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">User ID (Interne / Telegram):</span>
                        <span className="font-mono text-white font-semibold">{selectedUser.user_id}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Adresse Email:</span>
                        <span className="font-mono text-white">{selectedUser.identity?.email || "Non lié"}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Nom d&apos;affichage:</span>
                        <span className="text-white font-semibold">{selectedUser.identity?.display_name || "N/A"}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Pseudonyme Telegram:</span>
                        <span className="font-mono text-sky-300">{selectedUser.identity?.telegram_handle || "N/A"}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Fournisseur Auth:</span>
                        <span className="font-mono text-white uppercase">{selectedUser.identity?.auth_provider}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Google Sub ID:</span>
                        <span className="font-mono text-slate-300">
                          {selectedUser.identity?.google_sub || "Aucun"}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Langue / Timeframe / Risque:</span>
                        <span className="font-mono text-white">
                          {selectedUser.identity?.lang?.toUpperCase()} / {selectedUser.identity?.preferred_timeframe} /{" "}
                          {selectedUser.identity?.risk_profile}
                        </span>
                      </div>
                      <div className="flex justify-between py-1">
                        <span className="text-slate-400">Compte créé le:</span>
                        <span className="font-mono text-slate-200">{formatTs(selectedUser.identity?.created_at)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Legal Consent & Terms Proof */}
                  <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2.5">
                    <div className="text-xs font-bold text-emerald-400 uppercase font-mono flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4" /> Preuve de Consentement CGU &amp; Collecte
                    </div>
                    <div className="space-y-1.5 text-xs">
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Termes &amp; Conditions acceptés:</span>
                        <span
                          className={`font-mono font-bold ${
                            selectedUser.consent?.terms_accepted ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {selectedUser.consent?.terms_accepted ? "OUI (Consentement explicite)" : "NON"}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Consentement collecte données:</span>
                        <span
                          className={`font-mono font-bold ${
                            selectedUser.consent?.data_collection_consent ? "text-emerald-400" : "text-amber-400"
                          }`}
                        >
                          {selectedUser.consent?.data_collection_consent ? "AUTORISÉ" : "Partiel / Ancien compte"}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Version du contrat signée:</span>
                        <span className="font-mono text-amber-300">v{selectedUser.consent?.terms_version || "2.2.0"}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Date &amp; Heure de signature:</span>
                        <span className="font-mono text-white">{formatTs(selectedUser.consent?.terms_accepted_at)}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Adresse IP à la signature:</span>
                        <span className="font-mono text-sky-300">
                          {selectedUser.consent?.terms_accepted_ip || selectedUser.network_location?.ip_address || "N/A"}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Permission GPS Navigateur:</span>
                        <span className="font-mono text-white uppercase">
                          {selectedUser.consent?.geolocation_permission || "prompt"}
                        </span>
                      </div>
                      <div className="flex justify-between py-1">
                        <span className="text-slate-400">Quotas utilisés aujourd&apos;hui:</span>
                        <span className="font-mono text-slate-200">
                          Analyses: {selectedUser.subscription?.daily_analyses_used} | Scans:{" "}
                          {selectedUser.subscription?.daily_scans_used} | Paper:{" "}
                          {selectedUser.subscription?.daily_paper_trades_used}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* SUB-TAB 2: DEVICE, OS, IP & GEOLOCATION */}
              {activeSubTab === "device" && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Network, IP & Geolocation */}
                  <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2.5">
                    <div className="text-xs font-bold text-sky-400 uppercase font-mono flex items-center gap-2">
                      <MapPin className="w-4 h-4" /> Adresse IP, Réseau &amp; Localisation
                    </div>
                    <div className="space-y-1.5 text-xs">
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Adresse IP actuelle:</span>
                        <span className="font-mono text-amber-300 font-bold">
                          {selectedUser.network_location?.ip_address || "Inconnue"}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Pays / Région / Ville:</span>
                        <span className="font-mono text-white">
                          {[
                            selectedUser.network_location?.country,
                            selectedUser.network_location?.region,
                            selectedUser.network_location?.city,
                          ]
                            .filter(Boolean)
                            .join(" / ") || "Déduit via fuseau horaire"}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Fuseau horaire (Timezone):</span>
                        <span className="font-mono text-sky-300">
                          {selectedUser.network_location?.timezone || "N/A"}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Coordonnées GPS exactes:</span>
                        <span className="font-mono text-emerald-400">
                          {selectedUser.network_location?.latitude != null &&
                          selectedUser.network_location?.longitude != null
                            ? `${Number(selectedUser.network_location.latitude).toFixed(5)}, ${Number(
                                selectedUser.network_location.longitude
                              ).toFixed(5)} (±${Math.round(
                                selectedUser.network_location.location_accuracy_m || 0
                              )}m)`
                            : "Non partagées par le navigateur"}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Source de localisation:</span>
                        <span className="font-mono text-slate-300">
                          {selectedUser.network_location?.location_source || "IP / Timezone"}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Fournisseur (ISP / Réseau):</span>
                        <span className="font-mono text-slate-300">
                          {selectedUser.network_location?.isp || "Standard"} (
                          {selectedUser.network_location?.connection_type || "N/A"})
                        </span>
                      </div>
                      <div className="py-1">
                        <div className="text-slate-400 mb-1">
                          Historique complet des adresses IP ({selectedUser.network_location?.ip_history?.length || 0}):
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {(selectedUser.network_location?.ip_history || []).map((ipItem: string, idx: number) => (
                            <span
                              key={idx}
                              className="px-2 py-0.5 rounded bg-slate-900 border border-slate-700 font-mono text-[11px] text-slate-200"
                            >
                              {ipItem}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Hardware & Device Telemetry */}
                  <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2.5">
                    <div className="text-xs font-bold text-emerald-400 uppercase font-mono flex items-center gap-2">
                      <Cpu className="w-4 h-4" /> Type d&apos;Appareil, OS &amp; Empreinte Matérielle
                    </div>
                    <div className="space-y-1.5 text-xs">
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Type d&apos;appareil:</span>
                        <span className="font-mono text-white font-bold">
                          {selectedUser.device?.device_type || "Inconnu"} ({selectedUser.device?.device_vendor_model || "N/A"})
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Système d&apos;exploitation (OS):</span>
                        <span className="font-mono text-white">
                          {selectedUser.device?.os_name} {selectedUser.device?.os_version}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Navigateur Web:</span>
                        <span className="font-mono text-sky-300">
                          {selectedUser.device?.browser_name} {selectedUser.device?.browser_version}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Écran / Viewport / Pixel Ratio:</span>
                        <span className="font-mono text-white">
                          {selectedUser.device?.screen_resolution || "N/A"} /{" "}
                          {selectedUser.device?.viewport_size || "N/A"} (@{selectedUser.device?.pixel_ratio || 1}x)
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">CPU (Cœurs) / RAM / Tactile:</span>
                        <span className="font-mono text-white">
                          {selectedUser.device?.hardware_concurrency || "?"} cœurs /{" "}
                          {selectedUser.device?.device_memory ? `${selectedUser.device.device_memory} Go` : "? Go"} /{" "}
                          {selectedUser.device?.max_touch_points || 0} pts
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Batterie:</span>
                        <span className="font-mono text-slate-200">
                          {selectedUser.device?.battery_level != null
                            ? `${selectedUser.device.battery_level}% (${
                                selectedUser.device.battery_charging ? "En charge" : "Sur batterie"
                              })`
                            : "Non exposé par l'OS"}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Langues du navigateur:</span>
                        <span className="font-mono text-slate-300">
                          {selectedUser.device?.browser_languages || selectedUser.device?.browser_language || "N/A"}
                        </span>
                      </div>
                      <div className="py-1">
                        <div className="text-slate-400 mb-1">Chaîne User-Agent brute:</div>
                        <div className="p-2 rounded bg-slate-900 border border-slate-800 font-mono text-[10px] text-slate-300 break-all">
                          {selectedUser.device?.user_agent || "Aucun User-Agent enregistré"}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* SUB-TAB 3: SENSITIVE & SECURITY DATA */}
              {activeSubTab === "sensitive" && (
                <div className="space-y-4">
                  <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5 text-xs text-rose-200">
                      <Lock className="w-4 h-4 text-rose-400 shrink-0" />
                      <span>
                        <strong>Section Données Sensibles &amp; Cryptographiques :</strong> Utilisez le bouton{" "}
                        <em>« Afficher les données sensibles »</em> en haut à droite pour révéler les clés API
                        déchiffrées, les empreintes de sécurité et les jetons de session.
                      </span>
                    </div>
                    <button
                      onClick={() => setRevealSensitive((prev) => !prev)}
                      className="px-3 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/40 text-rose-200 text-xs font-bold shrink-0"
                    >
                      {revealSensitive ? "Masquer" : "Révéler tout"}
                    </button>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Binance API Keys & Encryption */}
                    <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2.5">
                      <div className="text-xs font-bold text-rose-400 uppercase font-mono flex items-center gap-2">
                        <Key className="w-4 h-4" /> Clés API Binance &amp; Secrets
                      </div>
                      <div className="space-y-1.5 text-xs">
                        <div className="flex justify-between py-1 border-b border-slate-800/60">
                          <span className="text-slate-400">Compte Binance lié:</span>
                          <span className="font-mono font-bold text-white">
                            {selectedUser.sensitive_security?.binance_credentials?.configured ? "OUI" : "NON"}
                          </span>
                        </div>
                        <div className="flex justify-between py-1 border-b border-slate-800/60">
                          <span className="text-slate-400">Environnement:</span>
                          <span className="font-mono text-amber-300">
                            {selectedUser.sensitive_security?.binance_credentials?.is_testnet
                              ? "TESTNET (Simulation)"
                              : "LIVE PRODUCTION"}
                          </span>
                        </div>
                        <div className="py-1 border-b border-slate-800/60">
                          <div className="text-slate-400 mb-1">Clé API Binance (API Key):</div>
                          <div className="p-2 rounded bg-slate-900 border border-slate-800 font-mono text-[11px] text-amber-300 break-all">
                            {revealSensitive
                              ? selectedUser.sensitive_security?.binance_credentials?.api_key_decrypted || "Aucune clé"
                              : selectedUser.sensitive_security?.binance_credentials?.api_key_masked || "Aucune clé"}
                          </div>
                        </div>
                        <div className="py-1 border-b border-slate-800/60">
                          <div className="text-slate-400 mb-1">Clé Secrète Binance (API Secret):</div>
                          <div className="p-2 rounded bg-slate-900 border border-slate-800 font-mono text-[11px] text-rose-300 break-all">
                            {revealSensitive
                              ? selectedUser.sensitive_security?.binance_credentials?.api_secret_decrypted ||
                                "Aucun secret"
                              : selectedUser.sensitive_security?.binance_credentials?.api_secret_masked ||
                                "Aucun secret"}
                          </div>
                        </div>
                        <div className="py-1">
                          <div className="text-slate-400 mb-1">Chiffrement en base (Ciphertext Fernet):</div>
                          <div className="p-2 rounded bg-slate-900 border border-slate-800 font-mono text-[10px] text-slate-400 break-all">
                            {selectedUser.sensitive_security?.binance_credentials?.api_key_ciphertext_preview || "N/A"}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Password Hash, PIN Code & Sessions */}
                    <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2.5">
                      <div className="text-xs font-bold text-amber-400 uppercase font-mono flex items-center gap-2">
                        <Shield className="w-4 h-4" /> Empreintes Mot de Passe, PIN &amp; Sessions
                      </div>
                      <div className="space-y-1.5 text-xs">
                        <div className="flex justify-between py-1 border-b border-slate-800/60">
                          <span className="text-slate-400">Algorithme Mot de Passe:</span>
                          <span className="font-mono text-emerald-400">
                            {selectedUser.sensitive_security?.password_algorithm}
                          </span>
                        </div>
                        <div className="py-1 border-b border-slate-800/60">
                          <div className="text-slate-400 mb-1">Hash du mot de passe (PBKDF2):</div>
                          <div className="p-2 rounded bg-slate-900 border border-slate-800 font-mono text-[10px] text-slate-300 break-all">
                            {revealSensitive
                              ? selectedUser.sensitive_security?.password_hash || "Non défini"
                              : selectedUser.sensitive_security?.password_hash
                              ? `${String(selectedUser.sensitive_security.password_hash).slice(0, 28)}...`
                              : "Non défini"}
                          </div>
                        </div>
                        <div className="flex justify-between py-1 border-b border-slate-800/60">
                          <span className="text-slate-400">Code PIN à 6 chiffres configuré:</span>
                          <span className="font-mono text-white font-bold">
                            {selectedUser.sensitive_security?.security_pin?.configured ? "OUI" : "NON"} (Échecs:{" "}
                            {selectedUser.sensitive_security?.security_pin?.failed_attempts || 0})
                          </span>
                        </div>
                        <div className="py-1 border-b border-slate-800/60">
                          <div className="text-slate-400 mb-1">Hash du Code PIN:</div>
                          <div className="p-2 rounded bg-slate-900 border border-slate-800 font-mono text-[10px] text-slate-300 break-all">
                            {revealSensitive
                              ? selectedUser.sensitive_security?.security_pin?.code_hash || "Aucun PIN"
                              : selectedUser.sensitive_security?.security_pin?.code_hash
                              ? `${String(selectedUser.sensitive_security.security_pin.code_hash).slice(0, 24)}...`
                              : "Aucun PIN"}
                          </div>
                        </div>
                        <div className="py-1">
                          <div className="text-slate-400 mb-1">
                            Sessions Web actives ({selectedUser.sensitive_security?.active_sessions_count || 0}):
                          </div>
                          <div className="space-y-1 max-h-28 overflow-y-auto">
                            {(selectedUser.sensitive_security?.sessions || []).map((s: any, idx: number) => (
                              <div
                                key={idx}
                                className="p-1.5 rounded bg-slate-900 border border-slate-800 font-mono text-[10px] text-slate-300 flex justify-between"
                              >
                                <span>Token: {s.token_preview}</span>
                                <span>IP: {s.ip_address || "N/A"}</span>
                                <span>{formatTs(s.created_at)}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* SUB-TAB 4: TRADING PORTFOLIOS (PAPER & LIVE) */}
              {activeSubTab === "trading" && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Paper Trading */}
                  <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2.5">
                    <div className="text-xs font-bold text-sky-400 uppercase font-mono flex items-center gap-2">
                      <DollarSign className="w-4 h-4" /> Portefeuille Paper Trading
                    </div>
                    <div className="space-y-1.5 text-xs">
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Capital disponible:</span>
                        <span className="font-mono text-white font-bold">
                          ${Number(selectedUser.trading?.paper_portfolio?.capital || 0).toFixed(2)} USDT
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">PnL Réalisé Total:</span>
                        <span
                          className={`font-mono font-bold ${
                            Number(selectedUser.trading?.paper_portfolio?.total_realized_pnl || 0) >= 0
                              ? "text-emerald-400"
                              : "text-rose-400"
                          }`}
                        >
                          ${Number(selectedUser.trading?.paper_portfolio?.total_realized_pnl || 0).toFixed(2)} USDT
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Positions Ouvertes / Fermées:</span>
                        <span className="font-mono text-white">
                          {selectedUser.trading?.paper_portfolio?.open_positions_count || 0} ouvertes /{" "}
                          {selectedUser.trading?.paper_portfolio?.closed_positions_count || 0} fermées (Winrate:{" "}
                          {selectedUser.trading?.paper_portfolio?.win_rate_pct || 0}%)
                        </span>
                      </div>
                      <div className="flex justify-between py-1">
                        <span className="text-slate-400">Watchlist active:</span>
                        <span className="font-mono text-amber-300">
                          {(selectedUser.trading?.watchlist || []).join(", ") || "Aucune"}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Live Trading & Config */}
                  <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2.5">
                    <div className="text-xs font-bold text-amber-400 uppercase font-mono flex items-center gap-2">
                      <Activity className="w-4 h-4" /> Trading Réel Binance &amp; Configuration
                    </div>
                    <div className="space-y-1.5 text-xs">
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Mode d&apos;exécution / Auto-Trade:</span>
                        <span className="font-mono text-white">
                          {selectedUser.trading?.config?.trading_mode?.toUpperCase()} / Auto:{" "}
                          {selectedUser.trading?.config?.auto_trade ? "ON" : "OFF"}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Risque par trade / Levier Max:</span>
                        <span className="font-mono text-white">
                          {selectedUser.trading?.config?.risk_per_trade}% / {selectedUser.trading?.config?.max_leverage}x
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-800/60">
                        <span className="text-slate-400">Ordres Live Ouverts / Fermés:</span>
                        <span className="font-mono text-white">
                          {selectedUser.trading?.live_trading?.open_trades_count || 0} ouverts /{" "}
                          {selectedUser.trading?.live_trading?.closed_trades_count || 0} fermés
                        </span>
                      </div>
                      <div className="flex justify-between py-1">
                        <span className="text-slate-400">PnL Live Réalisé:</span>
                        <span
                          className={`font-mono font-bold ${
                            Number(selectedUser.trading?.live_trading?.realized_pnl_usdt || 0) >= 0
                              ? "text-emerald-400"
                              : "text-rose-400"
                          }`}
                        >
                          ${Number(selectedUser.trading?.live_trading?.realized_pnl_usdt || 0).toFixed(2)} USDT
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* SUB-TAB 5: ACTIVITY, SIGNALS, ALERTS & SECURITY LOGS */}
              {activeSubTab === "activity" && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Security Audit Logs for this user */}
                  <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2.5">
                    <div className="text-xs font-bold text-rose-400 uppercase font-mono flex items-center gap-2">
                      <Shield className="w-4 h-4" /> Journal de Sécurité de l&apos;Utilisateur
                    </div>
                    <div className="space-y-1.5 max-h-60 overflow-y-auto">
                      {(selectedUser.activity?.security_events || []).length === 0 ? (
                        <div className="text-xs text-slate-500">Aucun événement de sécurité enregistré.</div>
                      ) : (
                        (selectedUser.activity?.security_events || []).map((ev: any, idx: number) => (
                          <div
                            key={idx}
                            className="p-2 rounded bg-slate-900 border border-slate-800 text-[11px] space-y-0.5"
                          >
                            <div className="flex justify-between font-mono">
                              <span className="text-amber-300 font-bold">{ev.event_type}</span>
                              <span className="text-slate-400">{formatTs(ev.created_at)}</span>
                            </div>
                            <div className="text-slate-300">{ev.details}</div>
                            <div className="text-[10px] font-mono text-slate-500">IP: {ev.ip_address || "N/A"}</div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Recent Signals, Alerts & Support Tickets */}
                  <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2.5">
                    <div className="text-xs font-bold text-sky-400 uppercase font-mono flex items-center gap-2">
                      <Bell className="w-4 h-4" /> Signaux Récents ({selectedUser.activity?.signals_count || 0}) &amp;
                      Tickets ({selectedUser.activity?.support_tickets?.length || 0})
                    </div>
                    <div className="space-y-1.5 max-h-60 overflow-y-auto">
                      {(selectedUser.activity?.recent_signals || []).map((sig: any, idx: number) => (
                        <div
                          key={idx}
                          className="p-2 rounded bg-slate-900 border border-slate-800 text-[11px] flex justify-between items-center"
                        >
                          <div>
                            <span className="font-mono font-bold text-white">{sig.symbol}</span>{" "}
                            <span className="px-1.5 py-0.5 rounded bg-slate-800 font-mono text-[10px] text-amber-300">
                              {sig.direction} ({sig.confidence}%)
                            </span>
                          </div>
                          <span className="font-mono text-[10px] text-slate-400">
                            ${Number(sig.entry_price || 0).toFixed(2)} • {formatTs(sig.timestamp)}
                          </span>
                        </div>
                      ))}
                      {(selectedUser.activity?.support_tickets || []).map((t: any, idx: number) => (
                        <div
                          key={`t-${idx}`}
                          className="p-2 rounded bg-amber-500/10 border border-amber-500/30 text-[11px] space-y-0.5"
                        >
                          <div className="font-bold text-amber-300 flex items-center gap-1">
                            <MessageSquare className="w-3 h-3" /> Ticket: {t.subject} ({t.status})
                          </div>
                          <div className="text-slate-300">{t.message}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { apiClaimSession, AuthApiError } from "@/lib/authApi";
import { useAuth } from "@/lib/authContext";
import {
  addVisitorMessage,
  createVisitorSession,
  deleteVisitorSession,
  getVisitorMessages,
  isSessionGone,
  VisitorMessage,
  VisitorSession,
} from "@/lib/api";

const storageKey = "smartcampus.visitor-session";

// ---------------------------------------------------------------------------
// Visitor chat panel (accessible without account)
// ---------------------------------------------------------------------------

function VisitorChat() {
  const { user, accessToken } = useAuth();
  const [session, setSession] = useState<VisitorSession | null>(null);
  const [messages, setMessages] = useState<VisitorMessage[]>([]);
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [remaining, setRemaining] = useState<number | null>(null);
  const [claimStatus, setClaimStatus] = useState<"idle" | "done" | "error">("idle");

  function resetSession(message: string) {
    sessionStorage.removeItem(storageKey);
    setSession(null);
    setMessages([]);
    setRemaining(null);
    setError(message);
  }

  function handleError(cause: unknown, fallback: string) {
    if (isSessionGone(cause)) {
      resetSession("Votre session a expiré ou n'existe plus. Commencez-en une nouvelle.");
      return;
    }
    setError(cause instanceof Error ? cause.message : fallback);
  }

  useEffect(() => {
    const stored = sessionStorage.getItem(storageKey);
    if (!stored) return;
    try {
      const restored = JSON.parse(stored) as VisitorSession;
      setSession(restored);
      setRemaining(restored.messages_remaining);
      getVisitorMessages(restored.session_id, restored.access_token)
        .then(setMessages)
        .catch((cause: unknown) => handleError(cause, "Échec de chargement."));
    } catch {
      sessionStorage.removeItem(storageKey);
      setError("La session locale est illisible. Créez-en une nouvelle.");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function startSession() {
    setBusy(true);
    setError("");
    try {
      const created = await createVisitorSession();
      sessionStorage.setItem(storageKey, JSON.stringify(created));
      setSession(created);
      setRemaining(created.message_limit);
      setMessages([]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Échec de création.");
    } finally {
      setBusy(false);
    }
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session || !content.trim()) return;
    setBusy(true);
    setError("");
    try {
      const added = await addVisitorMessage(
        session.session_id,
        session.access_token,
        content.trim(),
      );
      setMessages((cur) => [...cur, added.message].slice(-session.memory_limit));
      setRemaining(added.messages_remaining);
      const updated = { ...session, messages_remaining: added.messages_remaining };
      sessionStorage.setItem(storageKey, JSON.stringify(updated));
      setSession(updated);
      setContent("");
    } catch (cause) {
      handleError(cause, "Échec d'envoi.");
    } finally {
      setBusy(false);
    }
  }

  async function endSession() {
    if (!session) return;
    setBusy(true);
    setError("");
    try {
      await deleteVisitorSession(session.session_id, session.access_token);
      sessionStorage.removeItem(storageKey);
      setSession(null);
      setMessages([]);
      setRemaining(null);
    } catch (cause) {
      if (isSessionGone(cause)) { resetSession(""); return; }
      setError(cause instanceof Error ? cause.message : "Échec de suppression.");
    } finally {
      setBusy(false);
    }
  }

  // Claim the visitor session to the authenticated user's account
  async function claimSession() {
    if (!session || !accessToken) return;
    setBusy(true);
    try {
      await apiClaimSession(accessToken, session.session_id);
      setClaimStatus("done");
    } catch (cause) {
      setClaimStatus("error");
      setError(cause instanceof AuthApiError ? cause.message : "Échec de l'association.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <p className="eyebrow">Espace candidat</p>
      <h1>Conversation visiteur</h1>
      <p>
        La session est temporaire, liée à cet onglet et supprimable à tout
        moment. Le dialogue IA sera branché par un ticket ultérieur.
      </p>

      {!session ? (
        <button className="primary-button" onClick={startSession} disabled={busy}>
          {busy ? "Création…" : "Commencer sans compte"}
        </button>
      ) : (
        <>
          <p className="session-meta">
            Session valable jusqu&apos;au{" "}
            {new Date(session.expires_at).toLocaleString("fr-FR")} ·{" "}
            {remaining ?? session.message_limit} messages restants
          </p>

          {/* Claim banner: visible when user is logged in as candidat */}
          {user?.role === "candidat" && claimStatus === "idle" && (
            <div className="claim-banner" role="status">
              <p>
                Vous êtes connecté en tant que <strong>{user.full_name}</strong>.
                Voulez-vous associer cette session à votre compte ?
              </p>
              <button className="primary-button" onClick={claimSession} disabled={busy}>
                {busy ? "Association…" : "Associer au compte"}
              </button>
            </div>
          )}
          {claimStatus === "done" && (
            <p className="success-message">✔ Session associée à votre compte.</p>
          )}

          <div className="message-list" aria-live="polite">
            {messages.length === 0 ? (
              <p>Aucun message enregistré.</p>
            ) : (
              messages.map((m) => (
                <article className="message" key={m.id}>
                  <strong>{m.role === "user" ? "Vous" : "Assistant"}</strong>
                  <p>{m.content}</p>
                </article>
              ))
            )}
          </div>

          <form className="message-form" onSubmit={sendMessage}>
            <label htmlFor="visitor-message">Votre message</label>
            <textarea
              id="visitor-message"
              maxLength={4000}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              required
            />
            <div className="button-row">
              <button className="primary-button" disabled={busy || !content.trim()}>
                {busy ? "Envoi…" : "Enregistrer"}
              </button>
              <button
                className="secondary-button"
                type="button"
                disabled={busy}
                onClick={endSession}
              >
                Terminer et supprimer la session
              </button>
            </div>
          </form>
        </>
      )}
      {error && <p className="error-message" role="alert">{error}</p>}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Auth panel: login OR register
// ---------------------------------------------------------------------------

type AuthMode = "login" | "register";

function AuthPanel({ onSuccess }: { onSuccess: () => void }) {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Grab visitor session id if one exists, to pass on register
  function getVisitorSessionId(): string | undefined {
    try {
      const raw = sessionStorage.getItem("smartcampus.visitor-session");
      if (!raw) return undefined;
      const s = JSON.parse(raw) as { session_id: string };
      return s.session_id;
    } catch {
      return undefined;
    }
  }

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, fullName, password, getVisitorSessionId());
      }
      onSuccess();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Erreur.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <p className="eyebrow">Espace candidat</p>
      <h1>{mode === "login" ? "Connexion" : "Créer un compte"}</h1>

      <form className="auth-form" onSubmit={handleSubmit}>
        {mode === "register" && (
          <div className="form-field">
            <label htmlFor="full-name">Nom complet</label>
            <input
              id="full-name"
              type="text"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </div>
        )}
        <div className="form-field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="form-field">
          <label htmlFor="password">
            Mot de passe{mode === "register" ? " (8 caractères min.)" : ""}
          </label>
          <input
            id="password"
            type="password"
            required
            minLength={mode === "register" ? 8 : 1}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error && <p className="error-message" role="alert">{error}</p>}
        <div className="button-row">
          <button className="primary-button" disabled={busy}>
            {busy ? "Chargement…" : mode === "login" ? "Se connecter" : "Créer le compte"}
          </button>
        </div>
      </form>

      <p style={{ marginTop: "1rem", fontSize: "0.875rem" }}>
        {mode === "login" ? (
          <>
            Pas encore de compte ?{" "}
            <button className="link-button" onClick={() => setMode("register")}>
              Créer un compte candidat
            </button>
          </>
        ) : (
          <>
            Déjà un compte ?{" "}
            <button className="link-button" onClick={() => setMode("login")}>
              Se connecter
            </button>
          </>
        )}
      </p>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main page — switches between visitor chat and auth panel
// ---------------------------------------------------------------------------

type View = "chat" | "auth";

export default function CandidatePage() {
  const { user, logout, isLoading } = useAuth();
  const [view, setView] = useState<View>("chat");

  if (isLoading) {
    return (
      <main className="page-shell">
        <p>Chargement…</p>
      </main>
    );
  }

  return (
    <main className="page-shell">
      <div className="top-bar">
        <Link href="/" className="back-link">← Accueil</Link>
        {user ? (
          <span className="user-badge">
            {user.full_name} ({user.role}){" "}
            <button className="link-button" onClick={logout}>Se déconnecter</button>
          </span>
        ) : (
          <button
            className="link-button"
            onClick={() => setView(view === "auth" ? "chat" : "auth")}
          >
            {view === "auth" ? "← Retour au chat" : "Se connecter / Créer un compte"}
          </button>
        )}
      </div>

      {view === "auth" && !user ? (
        <AuthPanel onSuccess={() => setView("chat")} />
      ) : (
        <VisitorChat />
      )}
    </main>
  );
}

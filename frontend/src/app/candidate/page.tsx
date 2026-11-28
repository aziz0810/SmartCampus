"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

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

export default function CandidatePage() {
  const [session, setSession] = useState<VisitorSession | null>(null);
  const [messages, setMessages] = useState<VisitorMessage[]>([]);
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [remaining, setRemaining] = useState<number | null>(null);

  function resetSession(message: string) {
    sessionStorage.removeItem(storageKey);
    setSession(null);
    setMessages([]);
    setRemaining(null);
    setError(message);
  }

  function handleError(cause: unknown, fallback: string) {
    if (isSessionGone(cause)) {
      resetSession("Votre session a expiré ou n’existe plus. Commencez-en une nouvelle.");
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
      setMessages((current) => [...current, added.message].slice(-session.memory_limit));
      setRemaining(added.messages_remaining);
      const updatedSession = {
        ...session,
        messages_remaining: added.messages_remaining,
      };
      sessionStorage.setItem(storageKey, JSON.stringify(updatedSession));
      setSession(updatedSession);
      setContent("");
    } catch (cause) {
      handleError(cause, "Échec d’envoi.");
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
      if (isSessionGone(cause)) {
        resetSession("");
        return;
      }
      setError(cause instanceof Error ? cause.message : "Échec de suppression.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page-shell">
      <Link href="/" className="back-link">
        ← Accueil
      </Link>
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
              Session valable jusqu’au{" "}
              {new Date(session.expires_at).toLocaleString("fr-FR")} ·{" "}
              {remaining ?? session.message_limit} messages restants
            </p>
            <div className="message-list" aria-live="polite">
              {messages.length === 0 ? (
                <p>Aucun message enregistré.</p>
              ) : (
                messages.map((message) => (
                  <article className="message" key={message.id}>
                    <strong>{message.role === "user" ? "Vous" : "Assistant"}</strong>
                    <p>{message.content}</p>
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
                onChange={(event) => setContent(event.target.value)}
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
    </main>
  );
}

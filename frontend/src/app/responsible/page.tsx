"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/authContext";

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Erreur de connexion.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <p className="eyebrow">Espace responsable</p>
      <h1>Connexion requise</h1>
      <p>Cet espace est réservé aux responsables de formation.</p>

      <form className="auth-form" onSubmit={handleSubmit}>
        <div className="form-field">
          <label htmlFor="r-email">Email</label>
          <input
            id="r-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="form-field">
          <label htmlFor="r-password">Mot de passe</label>
          <input
            id="r-password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error && (
          <p className="error-message" role="alert">
            {error}
          </p>
        )}
        <div className="button-row">
          <button className="primary-button" disabled={busy}>
            {busy ? "Connexion…" : "Se connecter"}
          </button>
        </div>
      </form>
    </section>
  );
}

function ResponsibleDashboard() {
  const { user, logout } = useAuth();

  return (
    <section className="panel">
      <p className="eyebrow">Espace responsable</p>
      <h1>Portail de suivi</h1>
      <p>
        Bienvenue, <strong>{user?.full_name}</strong>. Vous êtes connecté avec
        le rôle <strong>responsable</strong>.
      </p>
      <p style={{ marginTop: "1rem", color: "#555" }}>
        Les fonctionnalités de suivi et de gestion seront disponibles dans les
        tickets dédiés.
      </p>
      <div className="button-row" style={{ marginTop: "2rem" }}>
        <button className="secondary-button" onClick={logout}>
          Se déconnecter
        </button>
      </div>
    </section>
  );
}

export default function ResponsiblePage() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <main className="page-shell">
        <Link href="/" className="back-link">← Accueil</Link>
        <p>Chargement…</p>
      </main>
    );
  }

  // Not logged in → show login form
  if (!user) {
    return (
      <main className="page-shell">
        <Link href="/" className="back-link">← Accueil</Link>
        <LoginForm />
      </main>
    );
  }

  // Logged in but wrong role
  if (user.role !== "responsable") {
    return (
      <main className="page-shell">
        <Link href="/" className="back-link">← Accueil</Link>
        <section className="panel">
          <p className="eyebrow">Accès refusé</p>
          <h1>Réservé aux responsables</h1>
          <p>
            Votre compte (<strong>{user.email}</strong>) n&apos;a pas le rôle
            &laquo; responsable &raquo;. Contactez un administrateur.
          </p>
        </section>
      </main>
    );
  }

  return (
    <main className="page-shell">
      <Link href="/" className="back-link">← Accueil</Link>
      <ResponsibleDashboard />
    </main>
  );
}

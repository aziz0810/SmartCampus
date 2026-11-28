import Link from "next/link";

export default function HomePage() {
  return (
    <main className="page-shell">
      <section className="hero">
        <p className="eyebrow">SmartCampus AI</p>
        <h1>Votre orientation commence ici.</h1>
        <p>
          Découvrez les espaces de la plateforme d’orientation de l’IIT et de
          l’ISB.
        </p>
        <nav className="card-grid" aria-label="Espaces">
          <Link className="nav-card" href="/candidate">
            <h2>Espace candidat</h2>
            <p>Commencer une conversation sans créer de compte.</p>
          </Link>
          <Link className="nav-card" href="/responsible">
            <h2>Espace responsable</h2>
            <p>Accéder au point d’entrée réservé aux responsables.</p>
          </Link>
        </nav>
      </section>
    </main>
  );
}

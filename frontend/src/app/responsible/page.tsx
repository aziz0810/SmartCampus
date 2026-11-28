import Link from "next/link";

export default function ResponsiblePage() {
  return (
    <main className="page-shell">
      <Link href="/" className="back-link">
        ← Accueil
      </Link>
      <section className="panel">
        <p className="eyebrow">Espace responsable</p>
        <h1>Portail de suivi</h1>
        <p>
          Le point d’entrée est prêt. L’authentification et les fonctionnalités
          réservées seront ajoutées dans les tickets dédiés.
        </p>
      </section>
    </main>
  );
}

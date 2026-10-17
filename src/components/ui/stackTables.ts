// Tableaux « empilés » sur mobile : pour chaque <table class="bs-stack">,
// recopie le texte de l'en-tête de colonne dans data-label de chaque cellule.
// Le CSS (.bs-stack dans index.css) transforme ensuite chaque ligne en carte
// en dessous de 768px. Sur desktop, le tableau reste inchangé.
function labelTable(table: HTMLTableElement): void {
  const headCells = Array.from(table.querySelectorAll<HTMLTableCellElement>('thead th'));
  if (headCells.length === 0) return;
  const labels: string[] = [];
  headCells.forEach((th) => {
    const span = Math.max(1, th.colSpan || 1);
    for (let i = 0; i < span; i += 1) labels.push((th.textContent || '').trim());
  });
  table.querySelectorAll<HTMLTableRowElement>('tbody tr').forEach((tr) => {
    let col = 0;
    Array.from(tr.cells).forEach((td) => {
      const span = Math.max(1, td.colSpan || 1);
      if (span === 1) {
        const label = labels[col] ?? '';
        if (td.getAttribute('data-label') !== label) td.setAttribute('data-label', label);
      }
      col += span;
    });
  });
}

function labelAll(): void {
  document.querySelectorAll<HTMLTableElement>('table.bs-stack').forEach(labelTable);
}

export function installStackTables(): void {
  if (typeof window === 'undefined' || typeof MutationObserver === 'undefined') return;
  let scheduled = false;
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(() => {
      scheduled = false;
      labelAll();
    });
  };
  new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
  schedule();
}

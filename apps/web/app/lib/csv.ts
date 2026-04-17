type CellValue = string | number | null | undefined;

function escapeCell(v: CellValue): string {
  const s = String(v ?? '');
  if (s.includes(',') || s.includes('"') || s.includes('\n') || s.includes('\r')) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

export function downloadCsv(rows: CellValue[][], filename: string): void {
  const content = '\ufeff' + rows.map((row) => row.map(escapeCell).join(',')).join('\r\n');
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function csvDate(): string {
  return new Date().toISOString().slice(0, 10);
}

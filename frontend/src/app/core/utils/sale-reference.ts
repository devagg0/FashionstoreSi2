/** Etiqueta de presentación; nunca reemplaza la referencia almacenada. */
export function formatSaleReference(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) return '—';
  const reference = value.trim();
  const match = /^(DIG-|VTA-)(.+)$/i.exec(reference);
  if (!match) return reference;
  const identifier = match[2].replace(/[^a-z0-9]/gi, '');
  return identifier.length > 8
    ? `${match[1].toUpperCase()}${identifier.slice(0, 8).toUpperCase()}`
    : reference;
}

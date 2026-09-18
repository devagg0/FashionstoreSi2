const formatter = new Intl.NumberFormat('es-BO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const formatBs = (value: string | number): string => `Bs ${formatter.format(Number(value))}`;

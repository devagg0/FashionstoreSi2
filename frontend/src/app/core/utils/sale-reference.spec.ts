import { formatSaleReference } from './sale-reference';

describe('formatSaleReference', () => {
  it('shortens long DIG identifiers to eight useful characters', () => {
    expect(formatSaleReference('DIG-696BFCA851E24A44AB1234567890ABCD')).toBe('DIG-696BFCA8');
    expect(formatSaleReference('DIG-696bfca8-51e2-4a44-ab12-34567890abcd')).toBe('DIG-696BFCA8');
  });
  it('shortens long VTA identifiers using the same format', () => {
    expect(formatSaleReference('VTA-12345678-9012-4321-8888-123456789012')).toBe('VTA-12345678');
  });
  it('preserves short and already formatted references', () => {
    for (const reference of ['DIG-31', 'VTA-31', 'DIG-696BFCA8']) {
      expect(formatSaleReference(reference)).toBe(reference);
    }
  });
  it('handles null, unexpected types and empty values', () => {
    for (const value of [null, undefined, 123, {}, [], '', '   ']) {
      expect(formatSaleReference(value)).toBe('—');
    }
    expect(formatSaleReference('OTRA-REFERENCIA')).toBe('OTRA-REFERENCIA');
  });
});

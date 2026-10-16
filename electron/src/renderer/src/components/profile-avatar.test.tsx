import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ProfileAvatar, profileInitials } from './profile-avatar';

describe('profile portraits', () => {
  it('uses first and last initials and handles empty and Unicode names', () => {
    expect(profileInitials('  Scarlet Rose  ')).toBe('SR');
    expect(profileInitials('Scarlet')).toBe('S');
    expect(profileInitials('')).toBe('♪');
    expect(profileInitials('Émilie Rose')).toBe('ÉR');
  });
  it('skips separators and brackets so initials are always letters', () => {
    expect(profileInitials('HI · Mood · Rona (Crying)')).toBe('HC');
    expect(profileInitials('Narrator (warm)')).toBe('NW');
    expect(profileInitials('· — ()')).toBe('♪');
    expect(profileInitials('हिंदी आवाज़')).toBe('हआ');
  });
  it('falls back to initials when the saved image cannot load', () => {
    const view = render(<ProfileAvatar name="Scarlet Rose" imageUrl="/profiles/one/image" />);
    fireEvent.error(view.container.querySelector('img')!);
    expect(screen.getByText('SR')).toBeInTheDocument();
  });
});

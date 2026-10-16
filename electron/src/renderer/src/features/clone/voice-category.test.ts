import { describe, expect, it } from 'vitest';
import { voiceCategories, voiceCategory } from './voice-category';

describe('voice categories from names', () => {
  it('reads the middle part of "Prefix · Group · Name"', () => {
    expect(voiceCategory('HI · Family · Didi (Elder Sister)')).toBe('Family');
    expect(voiceCategory('EN · Accent · British Male')).toBe('Accent');
  });
  it('reads the first part of "Group · Name" and ignores plain names', () => {
    expect(voiceCategory('AutoStory · Narrator')).toBe('AutoStory');
    expect(voiceCategory('Scarlet Rose')).toBeNull();
    expect(voiceCategory('Rock·Paper')).toBeNull();
    expect(voiceCategory('Male / Female')).toBeNull();
    expect(voiceCategory('')).toBeNull();
  });
  it('lists categories A–Z with counts', () => {
    expect(
      voiceCategories([
        'HI · Mood · Khush',
        'HI · Family · Maa',
        'HI · Mood · Rona',
        'Plain voice',
        'HI · Angry · Gussa',
      ]),
    ).toEqual([
      { name: 'Angry', count: 1 },
      { name: 'Family', count: 1 },
      { name: 'Mood', count: 2 },
    ]);
  });
});

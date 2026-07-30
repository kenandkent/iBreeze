import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SkillList } from './SkillList';
import type { Skill } from '../types';

const mockSkills: Skill[] = [
  {
    id: '1',
    name: 'Test Skill',
    version: '1.0.0',
    description: 'A test skill',
    category: 'testing',
    is_active: true,
  },
  {
    id: '2',
    name: 'Inactive Skill',
    version: '2.0.0',
    category: 'utility',
    is_active: false,
  },
];

describe('SkillList', () => {
  it('shows loading state', () => {
    render(<SkillList skills={[]} loading={true} />);
    expect(screen.getByText('Loading skills...')).toBeInTheDocument();
  });

  it('renders skill cards', () => {
    render(<SkillList skills={mockSkills} loading={false} />);
    expect(screen.getByText('Test Skill')).toBeInTheDocument();
    expect(screen.getByText('Inactive Skill')).toBeInTheDocument();
    expect(screen.getByText('v1.0.0')).toBeInTheDocument();
    expect(screen.getByText('v2.0.0')).toBeInTheDocument();
  });

  it('shows Active/Inactive badges', () => {
    render(<SkillList skills={mockSkills} loading={false} />);
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Inactive')).toBeInTheDocument();
  });

  it('renders description when present', () => {
    render(<SkillList skills={mockSkills} loading={false} />);
    expect(screen.getByText('A test skill')).toBeInTheDocument();
  });

  it('renders category', () => {
    render(<SkillList skills={mockSkills} loading={false} />);
    expect(screen.getByText('Category: testing')).toBeInTheDocument();
    expect(screen.getByText('Category: utility')).toBeInTheDocument();
  });

  it('renders empty list', () => {
    render(<SkillList skills={[]} loading={false} />);
    expect(screen.getByText('Skills')).toBeInTheDocument();
  });
});

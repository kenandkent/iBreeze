import type { Skill } from '../types';

interface SkillListProps {
  skills: Skill[];
  loading: boolean;
}

export function SkillList({ skills, loading }: SkillListProps) {
  if (loading) {
    return <div className="p-4">Loading skills...</div>;
  }

  return (
    <div className="p-4">
      <h2 className="text-lg font-semibold mb-4">Skills</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {skills.map((skill) => (
          <div key={skill.id} className="p-4 border rounded-lg">
            <div className="flex justify-between items-start">
              <div>
                <h3 className="font-medium">{skill.name}</h3>
                <p className="text-sm text-gray-500">v{skill.version}</p>
              </div>
              <span className={`px-2 py-1 text-xs rounded ${skill.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                {skill.is_active ? 'Active' : 'Inactive'}
              </span>
            </div>
            {skill.description && <p className="mt-2 text-sm">{skill.description}</p>}
            <p className="mt-2 text-xs text-gray-400">Category: {skill.category}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

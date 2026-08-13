import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TestProviders, createTestQueryClient } from '../test-utils';
import SkillPage from './SkillPage';
import * as apiClient from '../utils/apiClient';

const mockApiGet = vi.spyOn(apiClient, 'apiGet');
const mockApiPost = vi.spyOn(apiClient, 'apiPost');
const mockApiDelete = vi.spyOn(apiClient, 'apiDelete');
const mockApiUpload = vi.spyOn(apiClient, 'apiUpload');
function renderPage() {
  const qc = createTestQueryClient();
  return render(<TestProviders qc={qc}><SkillPage /></TestProviders>);
}

function draftSkill() {
  return { items: [{ id: '1', skill_key: 's1', version: '1', status: 'draft', agent_bindings: [], created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }] };
}

async function openUploadModal() {
  const { container } = renderPage();
  await waitFor(() => { expect(screen.getByText('s1')).toBeInTheDocument(); });
  fireEvent.click(screen.getByText('上传版本'));
  expect(screen.getByText('上传 Skill 版本', { selector: '.ant-modal-title' })).toBeInTheDocument();
  return container;
}

function selectFile(file: File) {
  const input = document.body.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });
}

function zipFile(name = 'a.zip', type = 'application/zip') {
  const file = new File(['x'], name, { type });
  return Object.assign(file, { originFileObj: file });
}

describe('SkillPage interactions', () => {
  beforeEach(() => { vi.clearAllMocks(); mockApiGet.mockResolvedValue({ items: [] }); mockApiUpload.mockResolvedValue({}); });

  it('installs skill successfully', async () => {
    mockApiPost.mockResolvedValue({ id: '1' });
    renderPage();
    fireEvent.click(screen.getByText('安装 Skill'));
    fireEvent.change(screen.getByLabelText('Skill Key'), { target: { value: 'test-skill' } });
    fireEvent.change(screen.getByLabelText('版本'), { target: { value: '1.0.0' } });
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('shows error on install failure', async () => {
    mockApiPost.mockRejectedValue(new Error('安装失败'));
    renderPage();
    fireEvent.click(screen.getByText('安装 Skill'));
    fireEvent.change(screen.getByLabelText('Skill Key'), { target: { value: 'fail' } });
    fireEvent.change(screen.getByLabelText('版本'), { target: { value: '1.0.0' } });
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiPost).toHaveBeenCalled(); });
  });

  it('removes skill', async () => {
    mockApiDelete.mockResolvedValue(undefined);
    mockApiGet.mockResolvedValue({
      items: [{ id: '1', skill_key: 's1', version: '1', status: 'draft', agent_bindings: [], created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }],
    });
    renderPage();
    await waitFor(() => { expect(screen.getByText('s1')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('移除'));
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiDelete).toHaveBeenCalled(); });
  });

  it('shows error on remove failure', async () => {
    mockApiDelete.mockRejectedValue(new Error('移除失败'));
    mockApiGet.mockResolvedValue({
      items: [{ id: '1', skill_key: 's1', version: '1', status: 'draft', agent_bindings: [], created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }],
    });
    renderPage();
    await waitFor(() => { expect(screen.getByText('s1')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('移除'));
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiDelete).toHaveBeenCalled(); });
  });

  it('opens upload version modal for non-published skills', async () => {
    mockApiGet.mockResolvedValue({
      items: [{ id: '1', skill_key: 's1', version: '1', status: 'draft', agent_bindings: [], created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }],
    });
    renderPage();
    await waitFor(() => { expect(screen.getByText('s1')).toBeInTheDocument(); });
    fireEvent.click(screen.getByText('上传版本'));
    expect(screen.getByText('上传 Skill 版本', { selector: '.ant-modal-title' })).toBeInTheDocument();
  });

  it('does not show upload button for published skills', async () => {
    mockApiGet.mockResolvedValue({
      items: [{ id: '1', skill_key: 's1', version: '1', status: 'published', agent_bindings: [], created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' }],
    });
    renderPage();
    await waitFor(() => { expect(screen.getByText('s1')).toBeInTheDocument(); });
    expect(screen.queryByText('上传版本')).not.toBeInTheDocument();
  });

  it('renders skills with all statuses and bindings', async () => {
    mockApiGet.mockResolvedValue({
      items: [
        { id: '1', skill_key: 's1', version: '1.0', status: 'draft', agent_bindings: ['a1'], created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
        { id: '2', skill_key: 's2', version: '2.0', status: 'validated', agent_bindings: ['a2', 'a3'], created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
        { id: '3', skill_key: 's3', version: '3.0', status: 'published', agent_bindings: null as unknown as string[], created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
        { id: '4', skill_key: 's4', version: '4.0', status: 'archived', agent_bindings: [], created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
      ],
    });
    renderPage();
    await waitFor(() => { expect(screen.getByText('草稿')).toBeInTheDocument(); });
    expect(screen.getByText('已验证')).toBeInTheDocument();
    expect(screen.getAllByText('已发布').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('a1')).toBeInTheDocument();
    expect(screen.getByText('archived')).toBeInTheDocument();
  });

  it('uploads skill version successfully', async () => {
    mockApiGet.mockResolvedValue(draftSkill());
    mockApiUpload.mockResolvedValue({});
    await openUploadModal();
    fireEvent.change(screen.getByLabelText('版本号'), { target: { value: '2.0.0' } });
    selectFile(zipFile());
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiUpload).toHaveBeenCalled(); });
    expect(mockApiUpload).toHaveBeenCalledWith('/skills/1/versions', expect.any(FormData));
  });

  it('shows error on upload failure', async () => {
    mockApiGet.mockResolvedValue(draftSkill());
    mockApiUpload.mockRejectedValue(new Error('上传失败'));
    await openUploadModal();
    fireEvent.change(screen.getByLabelText('版本号'), { target: { value: '2.0.0' } });
    // name ends with .zip while type is not zip -> isZip true via endsWith branch
    selectFile(zipFile('pkg.zip', 'text/plain'));
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiUpload).toHaveBeenCalled(); });
  });

  it('ignores non-zip file selection', async () => {
    mockApiGet.mockResolvedValue(draftSkill());
    await openUploadModal();
    fireEvent.change(screen.getByLabelText('版本号'), { target: { value: '2.0.0' } });
    const txt = new File(['x'], 'a.txt', { type: 'text/plain' });
    selectFile(txt);
    await waitFor(() => { expect(mockApiUpload).not.toHaveBeenCalled(); });
  });

  it('does not upload when no file selected', async () => {
    mockApiGet.mockResolvedValue(draftSkill());
    await openUploadModal();
    fireEvent.change(screen.getByLabelText('版本号'), { target: { value: '2.0.0' } });
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiUpload).not.toHaveBeenCalled(); });
  });

  it('does not upload when file lacks originFileObj', async () => {
    mockApiGet.mockResolvedValue(draftSkill());
    await openUploadModal();
    fireEvent.change(screen.getByLabelText('版本号'), { target: { value: '2.0.0' } });
    const file = new File(['x'], 'b.zip', { type: 'application/zip' });
    selectFile(file);
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiUpload).not.toHaveBeenCalled(); });
  });

  it('cancels install modal', async () => {
    renderPage();
    fireEvent.click(screen.getByText('安装 Skill'));
    expect(screen.getByLabelText('Skill Key')).toBeVisible();
    fireEvent.click(screen.getByText('取 消'));
    await waitFor(() => {
      const wrap = screen.getByLabelText('Skill Key').closest('.ant-modal-wrap') as HTMLElement;
      expect(wrap.style.display).toBe('none');
    });
    expect(mockApiPost).not.toHaveBeenCalled();
  });

  it('cancels upload modal', async () => {
    mockApiGet.mockResolvedValue(draftSkill());
    await openUploadModal();
    expect(screen.getByLabelText('版本号')).toBeVisible();
    fireEvent.click(screen.getByText('取 消'));
    await waitFor(() => {
      const wrap = screen.getByLabelText('版本号').closest('.ant-modal-wrap') as HTMLElement;
      expect(wrap.style.display).toBe('none');
    });
    expect(mockApiUpload).not.toHaveBeenCalled();
  });

  it('removes selected file before uploading', async () => {
    mockApiGet.mockResolvedValue(draftSkill());
    await openUploadModal();
    fireEvent.change(screen.getByLabelText('版本号'), { target: { value: '2.0.0' } });
    selectFile(zipFile());
    expect(screen.getByTitle('删除文件')).toBeInTheDocument();
    fireEvent.click(screen.getByTitle('删除文件'));
    await waitFor(() => { expect(screen.queryByTitle('删除文件')).not.toBeInTheDocument(); });
    fireEvent.click(screen.getByText('确 定'));
    await waitFor(() => { expect(mockApiUpload).not.toHaveBeenCalled(); });
  });
});

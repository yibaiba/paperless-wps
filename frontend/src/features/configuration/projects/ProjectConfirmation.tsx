import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Alert, App, Button, Form, Modal, Tag } from "antd";
import { api } from "../../../shared/api";
import type { ProjectConfiguration } from "../types";
import { AuthorFields, ROOT } from "../shared";

export function ProjectConfirmation({ projectId, saved, dirty, onConfirmed }: {
  projectId: string; saved: ProjectConfiguration; dirty: boolean; onConfirmed: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const { message } = App.useApp();
  const mutation = useMutation({
    mutationFn: (authored: { actor: string; evidence: string }) => api(`${ROOT}/projects/${projectId}/confirm`, { method: "POST", body: JSON.stringify({ ...authored, expected_revision: saved.revision, fingerprint: saved.fingerprint }) }),
    onSuccess: async () => { await onConfirmed(); setOpen(false); message.success("已记录该项目修订的人工确认"); },
    onError: (e) => message.error(e.message),
  });
  return <>
    {saved.confirmation ? <Tag color="green">v{saved.revision} 已由 {saved.confirmation.actor} 确认</Tag> : <Button disabled={dirty || !saved.revision || !saved.readiness.ready_for_confirmation} onClick={() => setOpen(true)}>确认已保存版本</Button>}
    <Modal open={open} title={`确认项目 v${saved.revision}`} footer={null} onCancel={() => setOpen(false)} destroyOnHidden>
      <Alert type="info" title="确认仅针对这个已保存修订" description="后续修改会形成新草稿，原确认版本保留。" />
      <Form layout="vertical" onFinish={(values) => mutation.mutate(values)}><AuthorFields /><Button type="primary" htmlType="submit" loading={mutation.isPending}>记录确认</Button></Form>
    </Modal>
  </>;
}

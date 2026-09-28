import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Form, Modal, Table } from "antd";
import { api } from "../../../shared/api";
import { AuthorFields, ROOT } from "../shared";
import { configurationKeys } from "../queryKeys";
import { definitionsKey } from "./useDefinitions";
interface Preview { fingerprint: string; rows: { id: string; name: string; existing: boolean; roles: { name: string }[]; rules: unknown[]; unresolved: string[] }[] }
export function DefinitionMapping() {
  const [open, setOpen] = useState(false);
  const client = useQueryClient(), { message } = App.useApp();
  const preview = useQuery({ queryKey: [...definitionsKey, "mapping-preview"], enabled: open, refetchOnWindowFocus: false,
    queryFn: () => api<Preview>(ROOT + "/definition-mapping-preview") });
  const apply = useMutation({
    mutationFn: (values: { actor: string; evidence: string }) => api(ROOT + "/definition-mapping-apply", { method: "POST", body: JSON.stringify({ ...values, fingerprint: preview.data!.fingerprint }) }),
    onSuccess: () => { client.invalidateQueries({ queryKey: definitionsKey }); client.invalidateQueries({ queryKey: configurationKeys.knowledge }); setOpen(false); message.success("已按明确名称建立映射，新定义仍为待核对"); },
    onError: (e) => message.error(e.message),
  });
  return <>
    <Button onClick={() => setOpen(true)}>从旧关系预览系统映射</Button>
    <Modal open={open} title="系统与角色身份映射预览" width={950} footer={null} onCancel={() => setOpen(false)} destroyOnHidden>
      <Alert type="info" title="按明确名称归集，不自动确认角色完整或软件互通" description="新定义保存为草稿；歧义项保留待核对。原关系和项目历史仍保留。" />
      {preview.error ? <Alert type="error" title={preview.error.message} /> : null}
      <Table rowKey="id" dataSource={preview.data?.rows} loading={preview.isLoading} columns={[
        { title: "原系统名称", dataIndex: "name" }, { title: "角色", render: (_, r) => r.roles.map((role) => role.name).join("、") },
        { title: "引用关系", render: (_, r) => r.rules.length }, { title: "处理", render: (_, r) => r.unresolved.join("；") || (r.existing ? "关联已有定义" : "创建待核对定义") },
      ]} />
      <Form layout="vertical" onFinish={(values) => apply.mutate(values)}><AuthorFields /><Button disabled={!preview.data} type="primary" htmlType="submit" loading={apply.isPending}>应用无歧义映射</Button></Form>
    </Modal>
  </>;
}

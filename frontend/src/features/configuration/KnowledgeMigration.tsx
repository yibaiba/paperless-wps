import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Modal, Space, Table, Tag, Typography } from "antd";
import { api } from "../../shared/api";
import { ROOT } from "./shared";

interface MigrationItem {
  legacy_rule: { id: string; revision: number; name: string; status: string };
  migration_state: "new" | "current" | "outdated";
  completion: "complete" | "incomplete";
  missing_fields: string[];
  unresolved: string[];
  blocking: string[];
  action?: "created" | "updated" | "unchanged" | "skipped";
}

export function KnowledgeMigration() {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const preview = useQuery({
    queryKey: ["configuration", "knowledge", "migration-preview"],
    enabled: open,
    queryFn: () => api<MigrationItem[]>(ROOT + "/knowledge/migration-preview"),
  });
  const apply = useMutation({
    mutationFn: () =>
      api<MigrationItem[]>(ROOT + "/knowledge/migration-apply", {
        method: "POST",
        body: JSON.stringify({ rule_ids: [] }),
      }),
    onSuccess: (items) => {
      queryClient.invalidateQueries({ queryKey: ["configuration"] });
      message.success(`旧规则已核对：${items.length} 条`);
    },
    onError: (error) => message.error(error.message),
  });
  return (
    <>
      <Button onClick={() => setOpen(true)}>旧规则迁移</Button>
      <Modal
        open={open}
        width={900}
        title="把旧配套规则并入搭配知识"
        onCancel={() => setOpen(false)}
        footer={
          <Space>
            <Button onClick={() => setOpen(false)}>关闭</Button>
            <Button
              type="primary"
              loading={apply.isPending}
              disabled={!preview.data?.length}
              onClick={() => apply.mutate()}
            >
              应用可迁移项目
            </Button>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          title="原规则和历史记录会保留，迁入后统一在搭配知识维护。"
          description="旧规则全部按草稿迁入；“每组”必须先确认是按系统、房间还是整个项目，不能直接启用。重复迁移不会生成第二条知识。"
        />
        {preview.error ? <Alert type="error" title={preview.error.message} /> : null}
        <Table<MigrationItem>
          size="small"
          loading={preview.isLoading}
          rowKey={(item) => item.legacy_rule.id}
          dataSource={apply.data ?? preview.data}
          columns={[
            {
              title: "旧规则",
              render: (_, item) => (
                <Space orientation="vertical" size={2}>
                  <Typography.Text>{item.legacy_rule.name}</Typography.Text>
                  <Typography.Text type="secondary">
                    v{item.legacy_rule.revision} · {item.legacy_rule.status}
                  </Typography.Text>
                </Space>
              ),
            },
            {
              title: "迁移状态",
              width: 130,
              render: (_, item) => (
                <Tag>
                  {item.action ??
                    { new: "待迁移", current: "已同步", outdated: "需要更新" }[
                      item.migration_state
                    ]}
                </Tag>
              ),
            },
            {
              title: "待确认",
              render: (_, item) =>
                [...item.unresolved, ...item.missing_fields].join("；") || "无",
            },
          ]}
        />
      </Modal>
    </>
  );
}

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Modal, Table } from "antd";
import { api } from "../../../shared/api";
import { ROOT } from "../shared";
import type { Configuration } from "../types";
import { ProjectRevisionDiff } from "./ProjectRevisionDiff";

interface Revision {
  revision: number;
  created_at: string;
  configuration: Configuration;
}
export function ProjectHistory({ entityId, projectId }: { entityId?: string; projectId: string }) {
  const [open, setOpen] = useState(false);
  const query = useQuery({
    queryKey: ["configuration", "history", entityId],
    enabled: open && !!entityId,
    queryFn: () => api<Revision[]>(ROOT + "/history/" + entityId),
  });
  return (
    <>
      <Button disabled={!entityId} onClick={() => setOpen(true)}>
        版本记录
      </Button>
      <Modal
        open={open}
        title="已保存的项目版本"
        width={850}
        footer={null}
        onCancel={() => setOpen(false)}
      >
        {query.error ? (
          <Alert type="error" title={query.error.message} />
        ) : null}
        <ProjectRevisionDiff projectId={projectId} revisions={query.data?.map((r) => r.revision) ?? []} />
        <Table
          rowKey="revision"
          dataSource={query.data}
          loading={query.isLoading}
          columns={[
            { title: "版本", dataIndex: "revision" },
            { title: "维护人", render: (_, r) => r.configuration.actor },
            { title: "依据", render: (_, r) => r.configuration.evidence },
            {
              title: "设备项",
              render: (_, r) => r.configuration.devices.length,
            },
          ]}
          expandable={{
            expandedRowRender: (r) => (
              <Table
                size="small"
                rowKey="id"
                pagination={false}
                dataSource={r.configuration.devices}
                columns={[
                  { title: "设备", dataIndex: "name" },
                  { title: "数量", dataIndex: "quantity" },
                  {
                    title: "配置版本",
                    render: (_, d) =>
                      `v${d.variant_snapshot?.revision ?? "未知"}`,
                  },
                ]}
              />
            ),
          }}
        />
      </Modal>
    </>
  );
}

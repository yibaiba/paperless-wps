import { useState } from "react";
import { ProductDrawer } from "../../catalog/ProductDrawer";
import { Alert, Button, Empty, Modal, Select, Space, Table } from "antd";
import type { useProjectEditor } from "./useProjectEditor";
export function ProjectImportDialog({
  editor,
}: {
  editor: ReturnType<typeof useProjectEditor>;
}) {
  const [source, setSource] = useState<string>();
  const {
    importOpen,
    setImportOpen,
    setPreview,
    preview,
    draft,
    config,
    topologyId,
    setTopologyId,
    topologies,
    importing,
  } = editor;
  return (
    <>
      <Modal
        width={850}
        title="预览旧资料导入"
        open={importOpen}
        onCancel={() => {
          setImportOpen(false);
          setPreview(undefined);
        }}
        onOk={() => {
          if (preview && !preview.unmapped.length) {
            draft.commit({
              ...preview.configuration,
              actor: config.actor,
              evidence: config.evidence,
            });
            setImportOpen(false);
            setPreview(undefined);
          }
        }}
        okText="采用预览配置"
        okButtonProps={{
          disabled:
            !preview || !!preview.unmapped.length || config.devices.length > 0,
        }}
      >
        <Alert
          type="info"
          title="导入到空配置，旧方案保留；未整理来源需先完成核对。"
        />
        <Space style={{ marginBlock: 16 }}>
          <Select
            style={{ width: 320 }}
            allowClear
            placeholder="本项目旧清单，或选择旧拓扑"
            value={topologyId}
            options={topologies.data?.map((t) => ({
              value: t.id,
              label: t.name,
            }))}
            onChange={setTopologyId}
          />
          <Button
            loading={importing.isPending}
            onClick={() => importing.mutate()}
          >
            生成预览
          </Button>
        </Space>
        {preview ? (
          <>
            <Alert
              type={preview.unmapped.length ? "warning" : "info"}
              title={`已映射 ${preview.configuration.devices.length} 项，未映射 ${preview.unmapped.length} 项`}
              description={preview.warning}
            />
            <Table
              rowKey="id"
              dataSource={preview.configuration.devices}
              columns={[
                { title: "设备", dataIndex: "name" },
                { title: "数量", dataIndex: "quantity" },
                {
                  title: "服务系统",
                  render: (_, d) =>
                    preview.configuration.requirements
                      .filter((r) => r.device_id === d.id)
                      .map(
                        (r) =>
                          preview.configuration.systems.find(
                            (s) => s.id === r.system_id,
                          )?.name,
                      )
                      .join("、"),
                },
                {
                  title: "资料来源",
                  render: (_, d) => (
                    <Button onClick={() => setSource(d.source_id)}>
                      查看原文
                    </Button>
                  ),
                },
              ]}
            />
            {preview.unmapped.length ? (
              <Table
                rowKey="id"
                dataSource={preview.unmapped}
                columns={[
                  { title: "未映射原因", dataIndex: "reason" },
                  {
                    title: "原始资料",
                    render: (_, r) => (
                      <Button onClick={() => setSource(r.source_id)}>
                        查看并核对来源
                      </Button>
                    ),
                  },
                ]}
              />
            ) : null}
          </>
        ) : (
          <Empty description="生成预览后再导入" />
        )}
      </Modal>
      <ProductDrawer id={source} onClose={() => setSource(undefined)} />
    </>
  );
}

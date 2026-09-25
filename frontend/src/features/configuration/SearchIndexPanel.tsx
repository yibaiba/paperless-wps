import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Progress,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import { api } from "../../shared/api";
import { ROOT, required } from "./shared";

interface SearchSettings {
  configured: boolean;
  embedding_url: string;
  embedding_model: string;
  reranker_url: string;
  reranker_model: string;
  has_key: boolean;
  embedding_dimensions: number;
  timeout_seconds: number;
  batch_size: number;
}
interface IndexStatus {
  configured: boolean;
  model: string;
  dimensions: number | null;
  total: number;
  indexed: number;
  stale: number;
  pending: number;
  failed: number;
}
interface IndexJob {
  id: string;
  status: string;
  error: string;
  updated_at: string;
  total: number;
  completed: number;
  skipped: number;
  embedding_model: string;
}

export function SearchIndexPanel() {
  const client = useQueryClient();
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const settings = useQuery({
    queryKey: ["configuration", "search", "settings"],
    queryFn: () => api<SearchSettings>(ROOT + "/search/settings"),
  });
  const status = useQuery({
    queryKey: ["configuration", "search", "status"],
    queryFn: () => api<IndexStatus>(ROOT + "/search/status"),
  });
  const jobs = useQuery({
    queryKey: ["configuration", "search", "jobs"],
    queryFn: () => api<IndexJob[]>(ROOT + "/search/jobs"),
    refetchInterval: (query) =>
      query.state.data?.some((job) => ["queued", "running"].includes(job.status))
        ? 2000
        : false,
  });
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["configuration", "search"] });
  };
  const save = useMutation({
    mutationFn: (values: object) =>
      api(ROOT + "/search/settings", {
        method: "PUT",
        body: JSON.stringify(values),
      }),
    onSuccess: () => {
      form.setFieldValue("api_key", "");
      refresh();
      message.success("智能检索设置已保存到后端私有配置");
    },
    onError: (error) => message.error(error.message),
  });
  const test = useMutation({
    mutationFn: () => api(ROOT + "/search/test", { method: "POST" }),
    onSuccess: () => message.success("Embedding 与 Reranker 连接验证通过"),
    onError: (error) => message.error(error.message),
  });
  const createJob = useMutation({
    mutationFn: () => api(ROOT + "/search/jobs", { method: "POST" }),
    onSuccess: () => {
      refresh();
      message.success("索引任务已进入队列");
    },
    onError: (error) => message.error(error.message),
  });
  const retry = useMutation({
    mutationFn: (id: string) =>
      api(`${ROOT}/search/jobs/${id}/retry`, { method: "POST" }),
    onSuccess: refresh,
    onError: (error) => message.error(error.message),
  });
  const error = settings.error || status.error || jobs.error;
  return (
    <Space orientation="vertical" size={16} style={{ width: "100%" }}>
      <Alert
        type="info"
        showIcon
        title="智能索引只负责召回和排序，兼容性与配套数量仍由搭配知识和 ZEN 检查。"
        description="保存产品不会自动调用模型。产品内容变化后会显示为待更新，由维护者手动建立索引。"
      />
      {error ? <Alert type="error" title={error.message} /> : null}
      <Card title="索引状态">
        <Space wrap size={32}>
          <Statistic title="已确认配置" value={status.data?.total ?? 0} />
          <Statistic title="索引可用" value={status.data?.indexed ?? 0} />
          <Statistic title="需要更新" value={status.data?.stale ?? 0} />
          <Statistic title="尚未建立" value={status.data?.pending ?? 0} />
          <Statistic title="失败" value={status.data?.failed ?? 0} />
        </Space>
        <Space style={{ marginTop: 16 }}>
          <Button
            type="primary"
            disabled={!settings.data?.configured}
            loading={createJob.isPending}
            onClick={() => createJob.mutate()}
          >
            建立或更新索引
          </Button>
          <Typography.Text type="secondary">
            后台执行命令：python -m presales.configuration.search.worker
          </Typography.Text>
        </Space>
      </Card>
      {settings.data ? (
        <Card title="本地模型接口">
          <Form
            key={`${settings.data.embedding_url}-${settings.data.reranker_url}`}
            form={form}
            layout="vertical"
            initialValues={{ ...settings.data, api_key: "" }}
            onFinish={(values) => save.mutate(values)}
            style={{ maxWidth: 760 }}
          >
            <Form.Item name="embedding_url" label="Embedding 完整接口地址" rules={required}>
              <Input placeholder="http://127.0.0.1:模型端口/v1/embeddings" />
            </Form.Item>
            <Form.Item name="embedding_model" label="Embedding 模型" rules={required}>
              <Input placeholder="Qwen3-Embedding-0.6B" />
            </Form.Item>
            <Form.Item name="reranker_url" label="Reranker 完整接口地址" rules={required}>
              <Input placeholder="http://127.0.0.1:模型端口/rerank" />
            </Form.Item>
            <Form.Item name="reranker_model" label="Reranker 模型" rules={required}>
              <Input placeholder="Qwen3-Reranker-0.6B" />
            </Form.Item>
            <Form.Item
              name="api_key"
              label={settings.data.has_key ? "密钥（已配置，留空保持）" : "密钥（本地服务可留空）"}
            >
              <Input.Password autoComplete="new-password" />
            </Form.Item>
            <Space wrap>
              <Form.Item name="embedding_dimensions" label="向量维度">
                <InputNumber disabled />
              </Form.Item>
              <Form.Item name="batch_size" label="索引批量">
                <InputNumber min={1} max={128} />
              </Form.Item>
              <Form.Item name="timeout_seconds" label="请求超时（秒）">
                <InputNumber min={1} />
              </Form.Item>
            </Space>
            <Space>
              <Button htmlType="submit" type="primary" loading={save.isPending}>
                保存设置
              </Button>
              <Button onClick={() => test.mutate()} loading={test.isPending}>
                测试真实连接
              </Button>
            </Space>
          </Form>
        </Card>
      ) : null}
      <Card title="索引任务">
        <Table<IndexJob>
          rowKey="id"
          dataSource={jobs.data}
          pagination={{ pageSize: 5 }}
          columns={[
            {
              title: "状态",
              render: (_, job) => <Tag>{job.status}</Tag>,
            },
            { title: "模型", dataIndex: "embedding_model" },
            {
              title: "进度",
              render: (_, job) => (
                <Progress
                  percent={job.total ? Math.round(((job.completed + job.skipped) / job.total) * 100) : 0}
                  size="small"
                  status={job.status === "failed" ? "exception" : undefined}
                />
              ),
            },
            { title: "错误", render: (_, job) => job.error || "—" },
            {
              title: "操作",
              render: (_, job) =>
                ["failed", "interrupted"].includes(job.status) ? (
                  <Button onClick={() => retry.mutate(job.id)}>重试</Button>
                ) : null,
            },
          ]}
        />
      </Card>
    </Space>
  );
}

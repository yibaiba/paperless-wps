import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Form, Input, InputNumber, Space } from "antd";
import { api } from "../../shared/api";
import { ROOT, required } from "./shared";
interface Settings {
  configured: boolean;
  base_url: string;
  model: string;
  has_key: boolean;
  timeout_seconds: number;
}
export function ModelSettings() {
  const client = useQueryClient();
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const query = useQuery({
    queryKey: ["configuration", "model-settings"],
    queryFn: () => api<Settings>(ROOT + "/extraction/settings"),
  });
  const save = useMutation({
    mutationFn: (values: object) =>
      api(ROOT + "/extraction/settings", {
        method: "PUT",
        body: JSON.stringify(values),
      }),
    onSuccess: () => {
      client.invalidateQueries({
        queryKey: ["configuration", "model-settings"],
      });
      form.setFieldValue("api_key", "");
      message.success("模型设置已保存到后端私有配置");
    },
    onError: (e) => message.error(e.message),
  });
  const test = useMutation({
    mutationFn: () => api(ROOT + "/extraction/test", { method: "POST" }),
    onSuccess: () => message.success("实际模型连接与 JSON 响应验证通过"),
    onError: (e) => message.error(e.message),
  });
  if (query.error) return <Alert type="error" title={query.error.message} />;
  return query.data ? (
    <Form
      key={query.data.base_url + query.data.model}
      form={form}
      layout="vertical"
      initialValues={{
        base_url: query.data.base_url,
        model: query.data.model,
        timeout_seconds: query.data.timeout_seconds,
        api_key: "",
      }}
      onFinish={(v) => save.mutate(v)}
      style={{ maxWidth: 680 }}
    >
      <Form.Item
        name="base_url"
        label="兼容接口地址（含版本路径，例如 /v1）"
        rules={required}
      >
        <Input placeholder="https://模型服务地址/v1" />
      </Form.Item>
      <Form.Item name="model" label="模型名称" rules={required}>
        <Input />
      </Form.Item>
      <Form.Item
        name="api_key"
        label={query.data.has_key ? "密钥（已配置，留空保持）" : "密钥"}
      >
        <Input.Password autoComplete="new-password" />
      </Form.Item>
      <Form.Item name="timeout_seconds" label="请求超时（秒）">
        <InputNumber min={1} />
      </Form.Item>
      <Space>
        <Button htmlType="submit" type="primary" loading={save.isPending}>
          保存设置
        </Button>
        <Button onClick={() => test.mutate()} loading={test.isPending}>
          测试已保存的连接
        </Button>
      </Space>
    </Form>
  ) : null;
}

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { App } from "antd";
import { api } from "../../../shared/api";
import type {
  Checked,
  Configuration,
  Deployment,
  ProjectConfiguration,
  Requirement,
  Suggestion,
} from "../types";
import { ROOT } from "../shared";
import { useConfigurationDraft } from "../useConfigurationDraft";
export function businessKey(c: Configuration) {
  const { drawing_xml, ...data } = c;
  void drawing_xml;
  return JSON.stringify(data);
}

export function useProjectEditor({
  projectId,
  initial,
}: {
  projectId: string;
  initial: ProjectConfiguration;
}) {
  const draft = useConfigurationDraft(initial.configuration),
    config = draft.present;
  const [saved, setSaved] = useState(initial);
  const savedJson = useRef(JSON.stringify(initial.configuration));
  const dirty = JSON.stringify(config) !== savedJson.current;
  const [checked, setChecked] = useState<Checked | undefined>(
    initial.fingerprint ? initial : undefined,
  );
  const [systemModal, setSystemModal] = useState(false),
    [author, setAuthor] = useState(false),
    [requirementModal, setRequirementModal] = useState<{
      systemId: string;
      initial?: Requirement;
    }>();
  const [selectedSystem, setSelectedSystem] = useState<string>(),
    [selectedRequirement, setSelectedRequirement] = useState<string>(),
    [deviceModal, setDeviceModal] = useState<string>();
  const [preview, setPreview] = useState<{
      configuration: Configuration;
      unmapped: { id: string; source_id: string; reason: string }[];
      warning: string;
    }>(),
    [importOpen, setImportOpen] = useState(false),
    [topologyId, setTopologyId] = useState<string>();
  const [tab, setTab] = useState("list");
  const { message, modal } = App.useApp();
  const navigate = useNavigate(),
    client = useQueryClient();
  const topologies = useQuery({
    queryKey: ["topologies"],
    enabled: importOpen,
    queryFn: () => api<{ id: string; name: string }[]>("/topologies"),
  });
  const drawing = useMutation({
    mutationFn: async ({
      next,
      addIds = [],
      removeId,
    }: {
      next: Configuration;
      addIds?: string[];
      removeId?: string;
    }) => {
      const result = await api<{ xml: string }>(ROOT + "/drawing", {
        method: "POST",
        body: JSON.stringify({
          xml: next.drawing_xml,
          devices: next.devices,
          add_ids: addIds,
          remove_device_id: removeId ?? null,
        }),
      });
      return { ...next, drawing_xml: result.xml };
    },
    onSuccess: (next) => draft.commit(next),
    onError: (e) => message.error(e.message),
  });
  const check = useMutation({
    mutationFn: (refresh: boolean) =>
      api<Checked>(ROOT + "/check", {
        method: "POST",
        body: JSON.stringify({
          configuration: draft.current.current,
          refresh_knowledge: refresh,
        }),
      }),
    onSuccess: (result) => {
      setChecked(result);
      draft.commit(result.configuration);
    },
    onError: (e) => message.error(e.message),
  });
  const save = useMutation({
    mutationFn: () =>
      api<ProjectConfiguration>(ROOT + "/projects/" + projectId, {
        method: "PUT",
        body: JSON.stringify({
          expected_revision: saved.revision,
          configuration: draft.current.current,
        }),
      }),
    onSuccess: (result) => {
      setSaved(result);
      client.setQueryData(["configuration", "project", projectId], result);
      savedJson.current = JSON.stringify(result.configuration);
      draft.commit(result.configuration);
      setChecked(result);
      client.invalidateQueries({ queryKey: ["project", projectId] });
      message.success("项目配置和清单已保存");
    },
    onError: (e) => message.error(e.message),
  });
  const apply = useMutation({
    mutationFn: ({
      suggestion,
      variantId,
      sourceId,
    }: {
      suggestion: Suggestion;
      variantId: string;
      sourceId: string;
    }) =>
      api<Checked>(ROOT + "/apply", {
        method: "POST",
        body: JSON.stringify({
          configuration: config,
          refresh_knowledge: false,
          fingerprint: checked!.fingerprint,
          suggestion_id: suggestion.id,
          variant_id: variantId,
          source_id: sourceId,
        }),
      }),
    onSuccess: (result) => {
      setChecked(result);
      drawing.mutate({
        next: result.configuration,
        addIds: result.configuration.devices
          .filter((d) => !config.devices.some((old) => old.id === d.id))
          .map((d) => d.id),
      });
    },
    onError: (e) => message.error(e.message),
  });
  const importing = useMutation({
    mutationFn: () =>
      api<typeof preview>(
        ROOT +
          `/projects/${projectId}/import-preview` +
          (topologyId ? "?topology_id=" + encodeURIComponent(topologyId) : ""),
      ),
    onSuccess: setPreview,
    onError: (e) => message.error(e.message),
  });
  const busy =
    drawing.isPending || check.isPending || save.isPending || apply.isPending;
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const requirement = config.requirements.find(
      (r) => r.id === selectedRequirement,
    ),
    editingDevice = config.devices.find((d) => d.id === deviceModal);
  const selectDevice = (device: Deployment, existing: boolean) => {
    if (!requirement) return;
    const previous = config.devices.find((d) => d.id === requirement.device_id);
    const replacing =
      !existing &&
      previous &&
      config.requirements.filter((r) => r.device_id === previous.id).length ===
        1;
    const chosen = replacing ? { ...device, id: previous.id } : device;
    const devices = existing
      ? config.devices
      : replacing
        ? config.devices.map((d) => (d.id === previous.id ? chosen : d))
        : [...config.devices, chosen];
    drawing.mutate({
      next: {
        ...config,
        devices,
        requirements: config.requirements.map((r) =>
          r.id === requirement.id ? { ...r, device_id: chosen.id } : r,
        ),
      },
      addIds: existing || replacing ? [] : [chosen.id],
    });
  };
  const saveProject = () => {
    if (!config.actor.trim() || !config.evidence.trim()) {
      setAuthor(true);
      return;
    }
    save.mutate();
  };
  const close = () => {
    if (dirty)
      modal.confirm({
        title: "离开会丢失当前未保存修改",
        okText: "放弃修改并离开",
        onOk: () => navigate("/projects/" + projectId),
      });
    else navigate("/projects/" + projectId);
  };
  const tree = config.rooms.map((room) => ({
    key: "room:" + room.id,
    title: room.name,
    children: config.systems
      .filter((s) => s.room_id === room.id)
      .map((s) => ({
        key: "system:" + s.id,
        title: s.name,
        children: config.requirements
          .filter((r) => r.system_id === s.id)
          .map((r) => ({
            key: "requirement:" + r.id,
            title: r.role + (r.device_id ? " · 已选" : " · 待选"),
          })),
      })),
  }));
  tree.push({
    key: "room:unassigned",
    title: "未分房间",
    children: config.systems
      .filter((s) => !s.room_id)
      .map((s) => ({
        key: "system:" + s.id,
        title: s.name,
        children: config.requirements
          .filter((r) => r.system_id === s.id)
          .map((r) => ({ key: "requirement:" + r.id, title: r.role })),
      })),
  });
  return {
    draft,
    config,
    saved,
    dirty,
    checked,
    systemModal,
    setSystemModal,
    author,
    setAuthor,
    requirementModal,
    setRequirementModal,
    selectedSystem,
    setSelectedSystem,
    setSelectedRequirement,
    setDeviceModal,
    preview,
    setPreview,
    importOpen,
    setImportOpen,
    topologyId,
    setTopologyId,
    tab,
    setTab,
    topologies,
    drawing,
    check,
    save,
    apply,
    importing,
    busy,
    requirement,
    editingDevice,
    selectDevice,
    saveProject,
    close,
    tree,
  };
}

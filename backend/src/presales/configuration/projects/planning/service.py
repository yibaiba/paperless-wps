from copy import deepcopy
from itertools import islice

from presales.configuration.common import view
from presales.lists.receipts import once
from presales.rules.calculation import digest
from presales.rules.repository import RuleConflict

from .context import PlanningContext
from .generator import generate_options
from .pricing import capture_prices


def proposal_summary(record, option=None):
    return dict(
        proposal_id=record["id"],
        draft_id=record["draft_id"],
        draft_revision=record["draft_revision"],
        fingerprint=record["fingerprint"],
        input_versions=record["input_versions"],
        deployment=record["deployment"],
        option=option_summary(option) if option else None,
        option_count=len(record["options"]),
        exhausted=record.get("exhausted", False),
        next_offset=None if record.get("exhausted") else len(record["options"]),
    )


def option_summary(option):
    quote = option["checked"].get("quotation_output") or {}
    return dict(
        id=option["id"],
        status=option["status"],
        standard=option["standard"],
        device_count=len(option["configuration"]["devices"]),
        question_count=len(option["questions"]),
        total=quote.get("total"),
        known_subtotal=quote.get("known_subtotal"),
        removal_candidates=option["removal_candidates"],
    )


class ProposalService:
    def __init__(self, lists):
        self.lists = lists
        self.repository = lists.repository
        self.entities = lists.entities
        self.session = lists.session

    def plan(self, request):
        return once(
            self.session,
            namespace="list_plan",
            request=request,
            perform=lambda: self._plan(request),
        )

    def _plan(self, request):
        draft = self.lists.locked(request)
        if request.proposal_id:
            proposal = self.entities.get(request.proposal_id, kind="list_proposal", lock=True)
            data = deepcopy(proposal.payload)
            if (data["draft_id"], data["draft_revision"], data["deployment"]) != (
                draft.id,
                draft.revision,
                request.deployment,
            ):
                raise RuleConflict("PROPOSAL_STALE：提案所用草稿或部署方式已变化，请重新生成")
            identity, revision = proposal.id, proposal.revision
        else:
            if request.option_offset:
                raise ValueError("读取替代方案请携带首次生成的提案 ID")
            data = self.new_payload(draft, request)
            created = self.entities.save("list_proposal", data)
            identity, revision = created["id"], created["revision"]
        if request.option_offset > len(data["options"]):
            raise ValueError("请按返回的 next_offset 读取替代方案")
        if request.option_offset == len(data["options"]) and not data["exhausted"]:
            context = PlanningContext(
                self.repository, data["baseline"], identity, data["deployment"]
            )
            stream = generate_options(context, prices=data["prices"])
            option = next(islice(stream, request.option_offset, None), None)
            if option is None:
                data["exhausted"] = True
            else:
                data["options"].append(option)
            record = self.entities.save(
                "list_proposal", data, entity_id=identity, expected_revision=revision
            )
        else:
            record = dict(id=identity, revision=revision, **data)
        option = (
            data["options"][request.option_offset]
            if request.option_offset < len(data["options"])
            else None
        )
        return proposal_summary(record, option)

    def new_payload(self, draft, request):
        configuration = deepcopy(draft.payload["configuration"])
        prices = capture_prices(self.session, configuration, self.repository.catalog.variants())
        versions = dict(
            catalog_snapshot_id=draft.payload["catalog_snapshot_id"],
            knowledge_snapshot_id=configuration["knowledge_snapshot_id"],
            definition_snapshot_id=configuration["definition_snapshot_id"],
            decision_runtime=configuration.get("decision_runtime", "python-v3"),
            decision_bundle_id=configuration.get("decision_bundle_id"),
            price_adoption_date=(configuration.get("quotation") or {}).get("price_adoption_date"),
            price_snapshot_fingerprint=digest(prices),
        )
        fingerprint = digest(
            [draft.id, draft.revision, configuration, versions, request.deployment]
        )
        return dict(
            draft_id=draft.id,
            draft_revision=draft.revision,
            baseline=configuration,
            input_versions=versions,
            fingerprint=fingerprint,
            deployment=request.deployment,
            prices=prices,
            options=[],
            exhausted=False,
        )

    def read(self, request, record):
        proposal = (
            view(self.entities.get(request.proposal_id, kind="list_proposal"))
            if request.proposal_id
            else None
        )
        if not proposal:
            matches = [
                p for p in self.entities.list("list_proposal") if p["draft_id"] == request.draft_id
            ]
            from presales.lists.queries import page

            return page([proposal_summary(p) for p in matches], request)
        if proposal["draft_id"] != request.draft_id:
            raise ValueError("提案不属于此草稿")
        result = dict(
            proposal_summary(proposal), stale=proposal["draft_revision"] != record["revision"]
        )
        from presales.lists.queries import page

        if request.view == "proposals":
            return dict(result, **page([option_summary(o) for o in proposal["options"]], request))
        option = next((o for o in proposal["options"] if o["id"] == request.option_id), None)
        if not option:
            raise ValueError("请指定已生成的方案 ID")
        views = dict(
            proposal_lines=option["checked"]["project_output"]["lines"],
            proposal_questions=option["questions"],
            proposal_decisions=option["decisions"],
            proposal_changes=option["changes"],
        )
        return dict(result, option=option_summary(option), **page(views[request.view], request))

"""Add source locators only. Preview by default; --apply uses normal batch revisions."""
import argparse
import json
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from presales.configuration.common import Entities
from presales.configuration.knowledge.batch_service import BatchApply, BatchPreview, KnowledgeChanges
from presales.configuration.knowledge.routes import save, validate_knowledge
from presales.configuration.knowledge.schemas import KnowledgeInput
from presales.storage import ProductRecord

ROOT = Path(__file__).resolve().parents[3]
SOURCE = '2026艾索软件产品及配套产品报价清单0604（V2.2）.xlsx'
OUTPUT = ROOT / 'outputs/core-closing'
# Existing conclusion status and all business fields remain unchanged.
REFERENCES = {
    'cd7e5e13-83a6-4866-8584-56bb471e0236': [('fc27e275-ceb7-484a-9098-9122702e3c9e', 'F17', '操作系统：支持Linux操作系统')],
    '507264c1-b7cd-4074-a8af-1928b458c09b': [('facc338e-f3f8-4de3-b8a2-a696f7292cb0', 'F18', '系统基于B/S架构，支持Linux环境下部署')],
    '51421c1f-6a71-55c5-908f-599e2b8163f2': [('7292073f-30e3-4dfa-8caa-e40f61a55f8b', 'I6', '因特尔处理器+优班图系统，50台终端以内使用'), ('37ee825a-8ddc-4e7b-840c-ff8c87532753', 'I7', '因特尔处理器+优班图系统，50-100台终端以使用')],
}
CAPACITY = [('3a9d4971-bcbd-4a74-85a6-57a9e80e8566', 'I3', '可适配：100-300台终端'), ('80279a36-06c5-47e0-afd0-1a38514d19bd', 'I4', '可适配：300-500台终端'), ('66d573b2-4754-4525-95ea-906bf666a844', 'I5', '可适配：500台以上终端')]
for identity in ('dc2f1547-3603-51a5-90aa-92b88ce42dac', '34e54b52-549b-59c9-88e2-a1a64f6b79a7', '373a8c85-b2da-57db-aba0-2abd0379b99f'):
    REFERENCES[identity] = CAPACITY


def preview(session):
    changes = []
    for identity, refs in REFERENCES.items():
        record = Entities(session).get(identity, kind='knowledge')
        data = KnowledgeInput.model_validate(record.payload).model_dump(mode='json')
        added = []
        for source_id, cell, quote in refs:
            source = session.get(ProductRecord, source_id)
            reference = dict(source_id=source_id, locator=f'{SOURCE} / {source.sheet}!{cell}', quote=quote)
            if reference not in data['evidence_refs']:
                added.append(reference)
        if not added:
            continue
        data['evidence_refs'] = [*data['evidence_refs'], *added]
        data['actor'] = '2026-10-03 原文出处核对'
        changes.append(dict(id=identity, expected_revision=record.revision, payload=data))
    return BatchPreview.model_validate(dict(items=changes)) if changes else None


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--apply', action='store_true')
    apply = args.parse_args().apply
    engine = create_engine(dotenv_values(ROOT / '.env')['DATABASE_URL'])
    with Session(engine) as session:
        service = KnowledgeChanges(session, validate=validate_knowledge, save=save)
        data = preview(session)
        if data is None:
            print('所有原文引用已经登记，没有重复修订。')
            return
        result = service.preview(data)
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / 'evidence-preview.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        if apply:
            result = service.apply(BatchApply(**data.model_dump(), fingerprint=result['fingerprint'], operation_id='core-closing-evidence-2026-10-03'))
            session.commit()
            (OUTPUT / 'evidence-applied.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(dict(applied=apply, changed=len(data.items)), ensure_ascii=False))
    engine.dispose()


if __name__ == '__main__':
    main()

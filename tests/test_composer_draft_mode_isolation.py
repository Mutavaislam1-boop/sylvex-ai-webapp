"""Saving a text composer must not overwrite the same account's image draft."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

@pytest.fixture
def draft_database(monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    import main
    rows={}
    class Cursor:
        def execute(self,sql,params):
            if 'INSERT INTO prostudio_drafts' in sql:
                owner,mode,conversation,text,attachment=params
                rows[owner,mode]=(mode,conversation,text,json.loads(attachment),datetime.now(timezone.utc))
            else:
                assert 'FROM prostudio_drafts' in sql
                self.owner=params[0]
        def fetchall(self):return [row for (owner,_),row in rows.items() if owner==self.owner]
        def close(self):pass
    class Connection:
        def cursor(self):return Cursor()
    @contextmanager
    def connection(_):yield Connection()
    monkeypatch.setattr(main,'DATABASE_URL','postgresql://dummy.invalid/isolated')
    monkeypatch.setattr(main,'db_connection',connection)
    monkeypatch.setattr(main,'ensure_prostudio_table',lambda:None)
    return main

@pytest.mark.parametrize('mode',['image','video','music','voice','text'])
def test_each_composer_mode_round_trips_without_overwriting_other_modes(draft_database,mode):
    main=draft_database
    for kind in ['image','video','music','voice','text']:
        result=main.save_prostudio_draft(101,kind,kind+' prompt',kind+' conversation',{'composer_draft':{'mode':kind}})
        assert result['mode']==kind
    drafts=main.load_prostudio_drafts(101)
    assert len(drafts)==5
    assert drafts[mode]['draft_text']==mode+' prompt'
    assert drafts[mode]['attachment']['composer_draft']['mode']==mode
    assert main.load_prostudio_drafts(202)=={}

def test_unknown_mode_keeps_existing_image_fallback(draft_database):
    assert draft_database.save_prostudio_draft(101,'unknown')['mode']=='image'

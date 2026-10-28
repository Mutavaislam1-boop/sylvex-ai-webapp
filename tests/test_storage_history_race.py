"""Actual PostgreSQL writer ordering, with synthetic URLs and no R2 calls."""
import asyncio
import json
import pytest
import main
from test_generation_result_postgres_roundtrip import result_database


def fixture_results(db):
    provider=['https://provider.example.test/a.png','https://provider.example.test/b.png']
    durable=['https://storage.example.test/generated/a.png','https://storage.example.test/generated/b.png']
    db.query("INSERT INTO prostudio_generation_jobs(id,status,cost) VALUES ('race-job','processing',19)")
    first={'ok':True,'type':'image','images':provider,'image_url':provider[0],'cost_credits':19,
        'storage_status':'pending','metadata':{'result_images':provider,'image_url':provider[0]}}
    assert main.update_prostudio_generation_job('race-job','completed',first)
    stored={'images':durable,'image_url':durable[0],
        'metadata':{'result_images':durable,'image_url':durable[0]}}
    history={'ok':True,'type':'image','images':provider,'image_url':provider[0],'cost_credits':19,
        'conversation_id':'race-conversation','message_id':501,
        'metadata':{'result_images':provider,'image_url':provider[0],'style':'cinematic','job_id':'race-job'}}
    return provider,durable,stored,history


def test_late_history_completion_cannot_overwrite_persisted_r2_urls(result_database):
    db=result_database;provider,durable,stored,history=fixture_results(db)
    main._merge_prostudio_storage_result('race-job',stored,'completed')
    assert main.update_prostudio_generation_job('race-job','completed',history,'','race-conversation')
    saved=db.query("SELECT result_json FROM prostudio_generation_jobs WHERE id='race-job'")[0][0]
    assert saved['images']==durable,'Late history write reverted already-persisted media'
    assert saved['storage_status']=='completed'
    assert saved['message_id']==501


def test_storage_completion_cannot_erase_history_reference_metadata(result_database):
    db=result_database;provider,durable,stored,history=fixture_results(db)
    assert main.update_prostudio_generation_job('race-job','completed',history,'','race-conversation')
    main._merge_prostudio_storage_result('race-job',stored,'completed')
    saved=db.query("SELECT result_json FROM prostudio_generation_jobs WHERE id='race-job'")[0][0]
    assert saved['images']==durable
    assert saved['metadata'].get('style')=='cinematic','Storage metadata replaced the whole history metadata object'
    assert saved['metadata']['result_images']==durable


def test_history_gallery_uses_committed_storage_result_after_provider_urls_expire(result_database):
    db=result_database
    db.query('ALTER TABLE prostudio_messages ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW()')
    db.query('ALTER TABLE prostudio_generation_jobs ADD COLUMN telegram_id BIGINT DEFAULT 101')
    provider,durable,stored,history=fixture_results(db)
    main.save_prostudio_message({'telegram_id':101,'conversation_id':'race-conversation','mode':'image'},history)
    main._merge_prostudio_storage_result('race-job',stored,'completed')
    gallery=asyncio.run(main.public_prostudio_gallery(telegram_id=101))
    assert len(gallery['items'])==1
    assert gallery['items'][0]['media_urls']==durable,'History kept only the temporary provider URLs'

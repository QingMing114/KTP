# Open WebUI Integration

`ktp_product` can be used as a standard OpenAI-compatible backend for Open WebUI.

## Admin Panel Configuration

In Open WebUI, add an external OpenAI-compatible connection and set:

- URL: `http://<UBUNTU_HOST_IP>:18080/v1`
- API Key: `sk-ktp-local`
- Model: `ktp-multi-agent`

This matches Open WebUI's documented OpenAI-compatible connection flow.

Prefer the standard backend-managed OpenAI connection first. Open WebUI's Direct Connections mode is optional and
would require CORS to be configured on `ktp_product` before browser clients can call it directly.

## Dataset Workflow

Register the dataset first:

```bash
curl -s http://127.0.0.1:18080/v2/datasets/register \
  -H 'Authorization: Bearer sk-ktp-local' \
  -H 'Content-Type: application/json' \
  -d '{
    "source_type":"local_path",
    "source_uri":"/tmp/ktp_baldness_real_flow/inputs/req-baldness-real-001_crop.tif",
    "display_name":"req-baldness-real-001_crop.tif",
    "region":"scalp",
    "crop_type":"hair",
    "task_type":"baldness_detection"
  }'
```

Then in Open WebUI chat, simply ask:

```text
请对 dataset:ds_xxx 做真实斑秃识别，并生成分析报告、置信度说明和可视化。
```

Because the dataset registry now persists default task context, the backend can resolve
`region/crop_type/task_type` from the stored dataset record.

## Automated Verification

```bash
cd /home/D/liumeng/ktp_product
/home/D/liumeng/miniconda3/envs/rsys/bin/python scripts/check_openai_dataset_chat.py \
  --api-key sk-ktp-local \
  --source-uri /tmp/ktp_baldness_real_flow/inputs/req-baldness-real-001_crop.tif \
  --message "请对这张头皮多光谱影像做真实斑秃识别，并生成分析报告、置信度说明和可视化。" \
  --region scalp \
  --crop-type hair \
  --task-type baldness_detection \
  --ref-mode text
```

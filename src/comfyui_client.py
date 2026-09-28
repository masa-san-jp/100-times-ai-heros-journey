"""ComfyUI のローカル API を使うストーリーボード画像生成クライアント。

通信、workflow の検証と入力注入、画像の保存処理は
100-times-ai-heroes の ``comfyui_image_gen.py`` を移植したもの。
ストーリーボードでは Qwen Image 2.1 Viggle Turbo workflow のみを扱い、
兄弟リポジトリにある SDXL 用の設定や clip skip は含めない。
"""

from __future__ import annotations

import copy
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence


class ComfyUIConfigurationError(ValueError):
    """ComfyUI または workflow/profile の設定が不正。"""


class ComfyUIConnectionError(ConnectionError):
    """ComfyUI へ接続できない。"""


class ComfyUITimeoutError(TimeoutError):
    """ComfyUI の処理がタイムアウトした。"""


class ComfyUIError(RuntimeError):
    """ComfyUI の処理に失敗した。"""


@dataclass(frozen=True)
class GeneratedImage:
    path: Path
    seed: int


STORYBOARD_WORKFLOW_FILENAME = "storyboard_qwen_image_2_1_turbo_api_workflow.json"
STORYBOARD_REFERENCE_WORKFLOW_FILENAME = (
    "storyboard_qwen_image_2_1_turbo_reference_api_workflow.json"
)

WORKFLOW_CONFIGS: Dict[str, Dict[str, Any]] = {
    STORYBOARD_WORKFLOW_FILENAME: {
        "required_nodes": {
            "1": "UNETLoader",
            "2": "CLIPLoader",
            "3": "VAELoader",
            "4": "TextEncodeQwenImage21",
            "5": "EmptyLatentImage",
            "10": "ViggleTurboLora",
            "11": "ViggleTurboSigmas",
            "12": "BasicGuider",
            "13": "KSamplerSelect",
            "14": "RandomNoise",
            "15": "SamplerCustomAdvanced",
            "7": "VAEDecode",
            "9": "SaveImage",
        },
        "injections": {
            "positive_prompt": {"node": "4", "input": "prompt"},
            "seed": {"node": "14", "input": "noise_seed"},
            "width": {"node": "5", "input": "width"},
            "height": {"node": "5", "input": "height"},
            "model_files": {
                "diffusion_models": {"node": "1", "input": "unet_name"},
                "text_encoders": {"node": "2", "input": "clip_name"},
                "vae": {"node": "3", "input": "vae_name"},
                "loras": {"node": "10", "input": "lora_name"},
            },
        },
    },
    STORYBOARD_REFERENCE_WORKFLOW_FILENAME: {
        "required_nodes": {
            "1": "UNETLoader",
            "2": "CLIPLoader",
            "3": "VAELoader",
            "5": "EmptyLatentImage",
            "10": "ViggleTurboLora",
            "11": "ViggleTurboSigmas",
            "12": "BasicGuider",
            "13": "KSamplerSelect",
            "14": "RandomNoise",
            "15": "SamplerCustomAdvanced",
            "18": "TextEncodeQwenImage21",
            "26": "LoadImage",
            "27": "LoadImage",
            "7": "VAEDecode",
            "9": "SaveImage",
        },
        "injections": {
            "positive_prompt": {"node": "18", "input": "prompt"},
            "seed": {"node": "14", "input": "noise_seed"},
            "width": {"node": "5", "input": "width"},
            "height": {"node": "5", "input": "height"},
            "reference_images": [
                {"node": "26", "input": "image"},
                {"node": "27", "input": "image"},
            ],
            "reference_connections": [
                {"node": "18", "input": "images.image_1", "source": ["26", 0]},
                {"node": "18", "input": "images.image_2", "source": ["27", 0]},
            ],
            "reference_encode_resolution": {"node": "18", "input": "resolution"},
            "model_files": {
                "diffusion_models": {"node": "1", "input": "unet_name"},
                "text_encoders": {"node": "2", "input": "clip_name"},
                "vae": {"node": "3", "input": "vae_name"},
                "loras": {"node": "10", "input": "lora_name"},
            },
        },
    },
}


def _default_profile_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "comfyui" / "storyboard_profiles.json"


def load_storyboard_profile(
    name: Optional[str] = None, path: Optional[Path] = None
) -> Dict[str, Any]:
    """ストーリーボード用 profile を読み込む。

    Args:
        name: profile 名。省略時は JSON の ``default_profile``。
        path: profile JSON。省略時は本リポジトリの既定ファイル。
    """
    profile_path = Path(path) if path is not None else _default_profile_path()
    try:
        with profile_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except OSError as exc:
        raise ComfyUIConfigurationError(
            f"Cannot read storyboard profile: {profile_path}"
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ComfyUIConfigurationError(
            f"Storyboard profile is not valid JSON: {profile_path}"
        ) from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("profiles"), dict):
        raise ComfyUIConfigurationError("Storyboard profile must contain a profiles object")
    profile_name = name or payload.get("default_profile")
    if not isinstance(profile_name, str) or not profile_name:
        raise ComfyUIConfigurationError("Storyboard profile has no default_profile")
    selected = payload["profiles"].get(profile_name)
    if not isinstance(selected, dict):
        raise ComfyUIConfigurationError(f"Unknown storyboard profile: {profile_name}")

    required = (
        "width",
        "height",
        "workflow_path",
        "reference_workflow_path",
        "license_name",
        "license_url",
    )
    if any(field not in selected for field in required):
        raise ComfyUIConfigurationError(
            f"Storyboard profile {profile_name} is missing a required field"
        )
    profile = copy.deepcopy(selected)
    profile["name"] = profile_name
    return profile


class ComfyUIImageGenerator:
    """ComfyUI API workflow を使ってストーリーボード画像を生成する。"""

    def __init__(
        self,
        base_url: str,
        workflow_path: Path,
        model_files: Optional[list[Any]] = None,
        reference_workflow_path: Optional[Path] = None,
        reference_encode_resolution: Optional[int] = None,
        width: int = 720,
        height: int = 400,
        timeout_seconds: float = 600.0,
        poll_interval_seconds: float = 1.0,
        opener: Optional[Callable[..., Any]] = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        seed_factory: Callable[[], int] = lambda: secrets.randbelow(2**63),
    ):
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme != "http" or parsed.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise ComfyUIConfigurationError(
                "COMFYUI_URL must point to a local HTTP server "
                "(127.0.0.1, localhost, or ::1)."
            )
        if not isinstance(width, int) or width <= 0 or width % 16:
            raise ComfyUIConfigurationError("Storyboard width must be a positive multiple of 16")
        if not isinstance(height, int) or height <= 0 or height % 16:
            raise ComfyUIConfigurationError("Storyboard height must be a positive multiple of 16")

        self.base_url = base_url.rstrip("/")
        self.workflow_path = Path(workflow_path)
        self.reference_workflow_path = (
            Path(reference_workflow_path) if reference_workflow_path else None
        )
        self.reference_encode_resolution = reference_encode_resolution
        self.model_files = list(model_files or [])
        self.width = width
        self.height = height
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.opener = opener or urllib.request.urlopen
        self.clock = clock
        self.sleeper = sleeper
        self.seed_factory = seed_factory

    def _workflow_config(self, workflow_path: Optional[Path] = None) -> Dict[str, Any]:
        selected_path = workflow_path or self.workflow_path
        # A custom filename is useful for tests and local variants, but it still
        # must be a storyboard-shaped workflow; no legacy SDXL fallback exists.
        return WORKFLOW_CONFIGS.get(selected_path.name, WORKFLOW_CONFIGS[STORYBOARD_WORKFLOW_FILENAME])

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request_bytes(
        self, request: urllib.request.Request, timeout: Optional[float] = None
    ) -> bytes:
        try:
            response = self.opener(request, timeout=timeout or self.timeout_seconds)
            try:
                return response.read()
            finally:
                close = getattr(response, "close", None)
                if close:
                    close()
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            raise ComfyUIConnectionError(
                f"Could not connect to ComfyUI at {self.base_url}: {exc}"
            ) from exc

    def _request_json(
        self, request: urllib.request.Request, timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        raw = self._request_bytes(request, timeout=timeout)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ComfyUIError("ComfyUI returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ComfyUIError("ComfyUI returned a JSON value instead of an object")
        return payload

    def check_connection(self) -> None:
        """画像生成開始前に ComfyUI へ接続できることを確認する。"""
        request = urllib.request.Request(self._url("system_stats"), method="GET")
        self._request_json(request, timeout=min(self.timeout_seconds, 10.0))

    def free_memory(self) -> None:
        """ComfyUI にロード済みモデルの解放を依頼する。"""
        body = json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8")
        request = urllib.request.Request(
            self._url("free"),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        self._request_bytes(request, timeout=min(self.timeout_seconds, 10.0))

    def _load_workflow(self, workflow_path: Optional[Path] = None) -> Dict[str, Any]:
        selected_path = workflow_path or self.workflow_path
        try:
            with selected_path.open("r", encoding="utf-8") as file:
                workflow = json.load(file)
        except OSError as exc:
            raise ComfyUIConfigurationError(
                f"Cannot read ComfyUI workflow: {selected_path}"
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ComfyUIConfigurationError(
                f"ComfyUI workflow is not valid JSON: {selected_path}"
            ) from exc

        if not isinstance(workflow, dict):
            raise ComfyUIConfigurationError("ComfyUI workflow must be a JSON object")
        for node_id, class_type in self._workflow_config(selected_path)["required_nodes"].items():
            node = workflow.get(node_id)
            if not isinstance(node, dict) or node.get("class_type") != class_type:
                raise ComfyUIConfigurationError(
                    f"Workflow node {node_id} must have class_type {class_type}"
                )
        return workflow

    @staticmethod
    def _set_input(
        workflow: Dict[str, Any], target: Optional[Dict[str, str]], value: Any
    ) -> bool:
        if not target:
            return False
        node = workflow.get(str(target.get("node")))
        if not isinstance(node, dict):
            return False
        inputs = node.get("inputs")
        input_name = target.get("input")
        if not isinstance(inputs, dict) or not input_name:
            return False
        inputs[input_name] = value
        return True

    def _require_input(
        self, workflow: Dict[str, Any], target: Optional[Dict[str, str]], value: Any, role: str
    ) -> None:
        if not self._set_input(workflow, target, value):
            raise ComfyUIConfigurationError(
                f"Workflow {self.workflow_path.name} has no injection target for {role}"
            )

    def _model_file_names(self) -> Dict[str, str]:
        names: Dict[str, str] = {}
        for model_file in self.model_files:
            if isinstance(model_file, dict):
                subdir = model_file.get("subdir")
                filename = model_file.get("filename")
            else:
                subdir = getattr(model_file, "subdir", None)
                filename = getattr(model_file, "filename", None)
            if subdir and filename:
                names[str(subdir)] = str(filename)
        return names

    def build_workflow(
        self,
        prompt: str,
        seed: int,
        width: Optional[int] = None,
        height: Optional[int] = None,
        workflow_path: Optional[Path] = None,
        reference_images: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """生成用の workflow を検証し、値を注入して返す。"""
        selected_path = workflow_path or self.workflow_path
        workflow = copy.deepcopy(self._load_workflow(selected_path))
        injections = self._workflow_config(selected_path)["injections"]
        model_file_names = self._model_file_names()
        targets = injections.get("model_files", {})
        for subdir, filename in model_file_names.items():
            self._require_input(
                workflow, targets.get(subdir), filename, f"model file ({subdir})"
            )
        if set(model_file_names) != set(targets):
            missing = sorted(set(targets) - set(model_file_names))
            if missing:
                raise ComfyUIConfigurationError(
                    f"Missing storyboard model files: {', '.join(missing)}"
                )

        self._require_input(workflow, injections.get("positive_prompt"), prompt, "positive prompt")
        self._require_input(workflow, injections.get("seed"), seed, "seed")
        for role, value in (
            ("width", self.width if width is None else width),
            ("height", self.height if height is None else height),
        ):
            if not isinstance(value, int) or value <= 0 or value % 16:
                raise ComfyUIConfigurationError(
                    f"Storyboard {role} must be a positive multiple of 16"
                )
            self._require_input(workflow, injections.get(role), value, role)

        if reference_images is not None:
            if self.reference_encode_resolution is not None:
                self._require_input(
                    workflow,
                    injections.get("reference_encode_resolution"),
                    self.reference_encode_resolution,
                    "reference encode resolution",
                )
            targets = injections.get("reference_images", [])
            connections = injections.get("reference_connections", [])
            if len(reference_images) > len(targets):
                raise ComfyUIConfigurationError(
                    f"Workflow supports at most {len(targets)} reference images"
                )
            for index, image_name in enumerate(reference_images):
                self._require_input(
                    workflow,
                    targets[index],
                    image_name,
                    f"reference image {index + 1}",
                )
                connection = connections[index]
                self._require_input(
                    workflow,
                    {"node": connection["node"], "input": connection["input"]},
                    connection["source"],
                    f"reference connection {index + 1}",
                )
        return workflow

    _build_workflow = build_workflow

    def _queue(self, workflow: Dict[str, Any]) -> str:
        request = urllib.request.Request(
            self._url("prompt"),
            data=json.dumps({"prompt": workflow}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        payload = self._request_json(request)
        prompt_id = payload.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            details = payload.get("node_errors") or payload
            raise ComfyUIError(f"ComfyUI did not return prompt_id: {details}")
        return prompt_id

    def _wait_for_history(
        self, prompt_id: str, timeout_seconds: Optional[float] = None
    ) -> Dict[str, Any]:
        timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            request = urllib.request.Request(
                self._url(f"history/{urllib.parse.quote(prompt_id, safe='')}")
            )
            history = self._request_json(request)
            result = history.get(prompt_id)
            if isinstance(result, dict):
                status = result.get("status") or {}
                status_string = status.get("status_str")
                if status_string == "success":
                    return result
                if status_string == "error" or status.get("completed") is False:
                    details = status.get("messages") or result.get("node_errors")
                    raise ComfyUIError(
                        f"ComfyUI failed for prompt {prompt_id}: {details}"
                    )
            self.sleeper(self.poll_interval_seconds)
        raise ComfyUITimeoutError(
            f"ComfyUI timed out after {timeout}s for prompt {prompt_id}"
        )

    @staticmethod
    def _first_image(history: Dict[str, Any]) -> Dict[str, str]:
        outputs = history.get("outputs") or {}
        if not isinstance(outputs, dict):
            raise ComfyUIError("ComfyUI history has no outputs object")
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            for image in node_output.get("images") or []:
                if isinstance(image, dict) and image.get("filename"):
                    return {
                        "filename": str(image["filename"]),
                        "subfolder": str(image.get("subfolder", "")),
                        "type": str(image.get("type", "output")),
                    }
        raise ComfyUIError("ComfyUI completed without returning an image")

    def _download_image(self, image: Dict[str, str]) -> bytes:
        data = self._request_bytes(
            urllib.request.Request(self._url(f"view?{urllib.parse.urlencode(image)}"))
        )
        if not data:
            raise ComfyUIError("ComfyUI returned an empty image")
        return data

    def upload_image(self, image_path: Path) -> str:
        """参照画像をアップロードし、LoadImage 用の名前を返す。"""
        path = Path(image_path)
        try:
            image_bytes = path.read_bytes()
        except OSError as exc:
            raise ComfyUIError(f"Cannot read reference image: {path}") from exc

        boundary = f"----CodexComfyUI{uuid.uuid4().hex}"
        boundary_bytes = boundary.encode("ascii")
        filename = path.name.replace('"', "_")
        parts = [
            b"--" + boundary_bytes + b"\r\n"
            + f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode("utf-8")
            + b"Content-Type: image/png\r\n\r\n"
            + image_bytes + b"\r\n",
            b"--" + boundary_bytes + b"\r\n"
            + b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n',
            b"--" + boundary_bytes + b"--\r\n",
        ]
        request = urllib.request.Request(
            self._url("upload/image"),
            data=b"".join(parts),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(sum(len(part) for part in parts)),
            },
            method="POST",
        )
        payload = self._request_json(request)
        name = payload.get("name")
        if not isinstance(name, str) or not name:
            raise ComfyUIError(f"ComfyUI upload did not return an image name: {payload}")
        subfolder = payload.get("subfolder", "")
        return f"{subfolder}/{name}" if subfolder else name

    upload_reference_image = upload_image

    def _save_image_bytes(self, image_bytes: bytes, output_dir: Path, filename_stem: str) -> Path:
        destination = Path(output_dir) / f"{filename_stem}.png"
        temporary = destination.with_suffix(".png.tmp")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("wb") as file:
                file.write(image_bytes)
            os.replace(temporary, destination)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise ComfyUIError(f"Cannot save generated image: {destination}") from exc
        return destination

    def generate(
        self,
        prompt: str,
        output_dir: Path,
        filename_stem: str,
        seed: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        reference_images: Optional[Sequence[Path]] = None,
    ) -> GeneratedImage:
        seed = self.seed_factory() if seed is None else seed
        reference_names: Optional[list[str]] = None
        workflow_path = self.workflow_path
        if reference_images:
            if self.reference_workflow_path is None:
                raise ComfyUIConfigurationError(
                    "Reference image generation is not configured for this profile"
                )
            reference_names = [self.upload_image(Path(path)) for path in reference_images]
            workflow_path = self.reference_workflow_path
        workflow = self.build_workflow(
            prompt,
            seed,
            width=width,
            height=height,
            workflow_path=workflow_path,
            reference_images=reference_names,
        )
        prompt_id = self._queue(workflow)
        history = self._wait_for_history(prompt_id)
        image_bytes = self._download_image(self._first_image(history))
        destination = self._save_image_bytes(image_bytes, output_dir, filename_stem)
        return GeneratedImage(path=destination, seed=seed)


# 兄弟リポジトリの呼び名を維持しつつ、用途が明確な別名も提供する。
ComfyUIClient = ComfyUIImageGenerator

from __future__ import annotations

import logging
from abc import ABC, abstractproperty
from collections.abc import Iterable
from pathlib import Path

from dynamicprompts.sampling_context import SamplingContext
from dynamicprompts.wildcards import WildcardManager
from dynamicprompts.wildcards.collection import structured
from dynamicprompts.wildcards.values import WildcardValues

logger = logging.getLogger(__name__)

INCLUDE_PREFIX = "include::"

_parse_structured_file_dict = structured._parse_structured_file_dict


def _parse_structured_file_dict_with_single_items(data: dict, **kwargs):
    """
    Treat "KEY: item" in YAML/JSON wildcard files as a wildcard with that single item ("KEY: [item]").
    Nested dicts come back through here because the library recurses via the module-level name.
    """
    data = {name: [value] if isinstance(value, str) else value for name, value in data.items()}
    return _parse_structured_file_dict(data, **kwargs)


structured._parse_structured_file_dict = _parse_structured_file_dict_with_single_items

_parse_structured_file_list = structured._parse_structured_file_list


def _parse_structured_file_list_with_leading_weights(value: list):
    """
    Split "weight::content" items on the first "::" instead of the library's last one, so
    that items containing "::" (e.g. "5::beach, [crabs::0.3]") don't break weight parsing.
    """
    items = []
    for item in value:
        if isinstance(item, str) and item[:1].isdigit():
            weight, sep, content = item.partition("::")
            try:
                if sep:
                    item = {"content": content, "weight": float(weight)}
            except ValueError:
                pass
        items.append(item)
    return _parse_structured_file_list(items)


structured._parse_structured_file_list = _parse_structured_file_list_with_leading_weights


class DPWildcardManager(WildcardManager):
    """
    Wildcard manager that replaces "include::<wildcard name>" entries with the entries of that wildcard,
    so each included item is as likely as an item listed directly.
    """

    def get_values(self, wildcard: str) -> WildcardValues:
        return self._get_values_with_includes(wildcard, ())

    def _get_values_with_includes(self, wildcard: str, chain: tuple[str, ...]) -> WildcardValues:
        if wildcard in chain:
            raise ValueError(f"Wildcard include loop: {' -> '.join((*chain, wildcard))}")

        values = []
        for item in super().get_values(wildcard):
            if isinstance(item, str) and item.startswith(INCLUDE_PREFIX):
                values.extend(self._get_values_with_includes(item[len(INCLUDE_PREFIX):].strip(), (*chain, wildcard)))
            else:
                values.append(item)
        return WildcardValues.from_items(values)


def find_wildcards_folder() -> Path:
    """
    Find the wildcards folder.
    First look in the ComfyUI base folder, then in this extension's folder in custom_nodes.
    """
    from folder_paths import base_path, folder_names_and_paths

    wildcard_path = Path(base_path) / "wildcards"

    if wildcard_path.exists():
        return wildcard_path

    extension_path = (
        Path(folder_names_and_paths["custom_nodes"][0][0])
        / "comfyui-dynamicprompts"
    )
    wildcard_path = extension_path / "wildcards"
    wildcard_path.mkdir(parents=True, exist_ok=True)

    return wildcard_path


class DPAbstractSamplerNode(ABC):
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "dynamicPrompts": False}),
                "seed": ("INT", {"default": 0, "display": "number"}),
                "autorefresh": (["Yes", "No"], {"default": "No"}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, text: str, seed: int, autorefresh: str):
        # Force re-evaluation of the node
        return float("NaN")

    RETURN_TYPES = ("STRING",)
    FUNCTION = "get_prompt"
    CATEGORY = "Dynamic Prompts"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reload_wildcards()
        self._current_prompt = None

    def _reload_wildcards(self) -> None:
        wildcards_folder = self._find_wildcards_folder()
        self._wildcard_manager = DPWildcardManager(path=wildcards_folder)

    def _find_wildcards_folder(self) -> Path | None:
        return find_wildcards_folder()

    def _get_next_prompt(self, prompts: Iterable[str], current_prompt: str) -> str:
        """
        Get the next prompt from the prompts generator.
        """
        try:
            return next(prompts)
        except (StopIteration, RuntimeError):
            self._prompts = self.context.sample_prompts(current_prompt)
            try:
                return next(self._prompts)
            except StopIteration:
                logger.exception("No more prompts to generate!")
                return ""

    def has_prompt_changed(self, text: str) -> bool:
        """
        Check if the prompt has changed.
        """
        return self._current_prompt != text

    def get_prompt(self, text: str, seed: int, autorefresh: str) -> tuple[str]:
        """
        Main entrypoint for this node.
        Using the sampling context, generate a new prompt.
        """

        if seed > 0:
            self.context.rand.seed(seed)

        if text.strip() == "":
            return ("",)

        if autorefresh == 'Yes':
            print(f"Autorefresh: {autorefresh}")
            self._reload_wildcards()
            self.context.wildcard_manager.clear_cache()
            self._current_prompt = text
            self._prompts = self.context.sample_prompts(self._current_prompt)
        else:
            if self.has_prompt_changed(text):
                self._current_prompt = text
                self._prompts = self.context.sample_prompts(self._current_prompt)

        if self._prompts is None:
            logger.exception("Something went wrong. Prompts is None!")
            return ("",)

        if self._current_prompt is None:
            logger.exception("Something went wrong. Current prompt is None!")
            return ("",)

        new_prompt = self._get_next_prompt(self._prompts, self._current_prompt)
        print(f"New prompt: {new_prompt}")

        return (str(new_prompt),)

    @abstractproperty
    def context(self) -> SamplingContext:
        ...

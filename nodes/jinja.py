import random

from dynamicprompts.generators import JinjaGenerator
from dynamicprompts.wildcards import WildcardManager

from .generator import DPGeneratorNode
from .sampler import find_wildcards_folder


class DPJinja(DPGeneratorNode):
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {"multiline": True}),
                "autorefresh": (["Yes", "No"],),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, text, autorefresh, seed):
        # Force re-evaluation of the node
        if autorefresh == "Yes":
            return float("NaN")

    def get_prompt(self, text: str, autorefresh: str, seed: int) -> tuple[str]:
        prompt = self.generate_prompt(text, seed)
        print(f"Prompt: {prompt}")

        return (prompt,)

    def generate_prompt(self, text, seed):
        wildcard_manager = WildcardManager(path=find_wildcards_folder())
        prompt_generator = JinjaGenerator(wildcard_manager=wildcard_manager)

        # random_sample() draws from the random generator's own Random instance,
        # while choice(), weighted_choice(), random() and randint() use the global random module
        prompt_generator._generators["random"]._context.rand.seed(seed)
        random.seed(seed)

        all_prompts = prompt_generator.generate(text, 1) or [""]
        return str(all_prompts[0])

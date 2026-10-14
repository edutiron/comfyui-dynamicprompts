from dynamicprompts.generators import JinjaGenerator
from dynamicprompts.wildcards import WildcardManager

from .generator import DPGeneratorNode
from .sampler import find_wildcards_folder


class DPJinja(DPGeneratorNode):
    def generate_prompt(self, text):
        wildcard_manager = WildcardManager(path=find_wildcards_folder())
        prompt_generator = JinjaGenerator(wildcard_manager=wildcard_manager)

        all_prompts = prompt_generator.generate(text, 1) or [""]
        return str(all_prompts[0])

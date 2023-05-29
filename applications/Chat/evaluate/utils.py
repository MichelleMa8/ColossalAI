import dataclasses
import logging
import math
import os
import io
import sys
import time
import json
import numpy as np
from typing import Optional, Sequence, Union

import openai
import tqdm
from openai import openai_object
import copy


import torch.distributed as dist

StrOrOpenAIObject = Union[str, openai_object.OpenAIObject]

# openai_org = os.getenv("OPENAI_ORG")
# if openai_org is not None:
#     openai.organization = openai_org
#     logging.warning(f"Switching to organization: {openai_org} for OAI API key.")

@dataclasses.dataclass
class OpenAIDecodingArguments(object):
    # max_tokens: int = 1800
    temperature: float = 0.2
    top_p: float = 1.0
    n: int = 1
    stream: bool = False
    stop: Optional[Sequence[str]] = None
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    # suffix: Optional[str] = None
    # logprobs: Optional[int] = None
    # echo: bool = False


def openai_completion(
    prompt,
    num_inst,
    decoding_args: OpenAIDecodingArguments,
    model_name="gpt-3.5-turbo",
    sleep_time=2,
    **decoding_kwargs,
):
    
    batch_decoding_args = copy.deepcopy(decoding_args)  # cloning the decoding_args
    
    while True:
        try:
            shared_kwargs = dict(
                    model=model_name,
                    **batch_decoding_args.__dict__,
                    **decoding_kwargs,
                )
            response = openai.ChatCompletion.create(messages=[{"role":"user","content":prompt}], **shared_kwargs)
            answer = response['choices'][0]
            break
        except openai.error.OpenAIError as e:
            logging.warning(f"OpenAIError: {e}.")
            if "Please reduce your prompt" in str(e):
                batch_decoding_args.max_tokens = int(batch_decoding_args.max_tokens * 0.8)
                logging.warning(f"Reducing target length to {batch_decoding_args.max_tokens}, Retrying...")
            else:
                logging.warning("Hit request rate limit; retrying...")
                time.sleep(sleep_time)  # Annoying rate limit on requests.

    # if return_text:
    #     completions = [completion.text for completion in completions]
    # if decoding_args.n > 1:
    #     # make completions a nested list, where each entry is a consecutive decoding_args.n of original entries.
    #     completions = [completions[i : i + decoding_args.n] for i in range(0, len(completions), decoding_args.n)]
    # if is_single_prompt:
    #     # Return non-tuple if only 1 input and 1 generation.
    #     (completions,) = completions
    return {"result": answer, "num_inst": num_inst}

def is_rank_0() -> bool:
    return not dist.is_initialized() or dist.get_rank() == 0

def _make_w_io_base(f, mode: str):
    if not isinstance(f, io.IOBase):
        f_dirname = os.path.dirname(f)
        if f_dirname != "":
            os.makedirs(f_dirname, exist_ok=True)
        f = open(f, mode=mode, encoding="utf-8")
    return f

def _make_r_io_base(f, mode: str):
    if not isinstance(f, io.IOBase):
        f = open(f, mode=mode)
    return f

def jdump(obj, f, mode="w", indent=4, default=str):
    """Dump a str or dictionary to a file in json format.
    Args:
        obj: An object to be written.
        f: A string path to the location on disk.
        mode: Mode for opening the file.
        indent: Indent for storing json dictionaries.
        default: A function to handle non-serializable entries; defaults to `str`.
    """
    f = _make_w_io_base(f, mode)
    if isinstance(obj, (dict, list)):
        json.dump(obj, f, indent=indent, default=default, ensure_ascii=False)
    elif isinstance(obj, str):
        f.write(obj)
    else:
        raise ValueError(f"Unexpected type: {type(obj)}")
    f.close()

def jload(f, mode="r"):
    """Load a .json file into a dictionary."""
    f = _make_r_io_base(f, mode)
    jdict = json.load(f)
    f.close()
    return jdict

def get_json_list(file_path):
    with open(file_path, 'r') as f:
        json_list = []
        for line in f:
            json_list.append(json.loads(line))
        return json_list

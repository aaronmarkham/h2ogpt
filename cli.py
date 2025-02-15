import copy
import torch

from generate import eval_func_param_names, get_score_model, get_model, evaluate, check_locals
from prompter import non_hf_types
from utils import clear_torch_cache, NullContext, get_kwargs


def run_cli(  # for local function:
        base_model=None, lora_weights=None,
        debug=None, chat_context=None,
        examples=None, memory_restriction_level=None,
        # for get_model:
        score_model=None, load_8bit=None, load_4bit=None, load_half=None, infer_devices=None, tokenizer_base_model=None,
        gpu_id=None, local_files_only=None, resume_download=None, use_auth_token=None,
        trust_remote_code=None, offload_folder=None, compile_model=None,
        # for some evaluate args
        stream_output=None, prompt_type=None, prompt_dict=None,
        temperature=None, top_p=None, top_k=None, num_beams=None,
        max_new_tokens=None, min_new_tokens=None, early_stopping=None, max_time=None, repetition_penalty=None,
        num_return_sequences=None, do_sample=None, chat=None,
        langchain_mode=None, document_choice=None, top_k_docs=None, chunk=None, chunk_size=None,
        # for evaluate kwargs
        src_lang=None, tgt_lang=None, concurrency_count=None, save_dir=None, sanitize_bot_response=None,
        model_state0=None, raise_generate_gpu_exceptions=None, load_db_if_exists=None, dbs=None, user_path=None,
        detect_user_path_changes_every_query=None,
        use_openai_embedding=None, use_openai_model=None, hf_embedding_model=None,
        db_type=None, n_jobs=None, first_para=None, text_limit=None, verbose=None, cli=None,
        # unique to this function:
        cli_loop=None,
):
    check_locals(**locals())

    score_model = ""  # FIXME: For now, so user doesn't have to pass
    n_gpus = torch.cuda.device_count() if torch.cuda.is_available else 0
    device = 'cpu' if n_gpus == 0 else 'cuda'
    context_class = NullContext if n_gpus > 1 or n_gpus == 0 else torch.device

    with context_class(device):
        from functools import partial

        # get score model
        smodel, stokenizer, sdevice = get_score_model(reward_type=True,
                                                      **get_kwargs(get_score_model, exclude_names=['reward_type'],
                                                                   **locals()))

        model, tokenizer, device = get_model(reward_type=False,
                                             **get_kwargs(get_model, exclude_names=['reward_type'], **locals()))
        model_state = [model, tokenizer, device, base_model]
        my_db_state = [None]
        fun = partial(evaluate, model_state, my_db_state,
                      **get_kwargs(evaluate, exclude_names=['model_state', 'my_db_state'] + eval_func_param_names,
                                   **locals()))

        example1 = examples[-1]  # pick reference example
        all_generations = []
        while True:
            clear_torch_cache()
            instruction = input("\nEnter an instruction: ")
            if instruction == "exit":
                break

            eval_vars = copy.deepcopy(example1)
            eval_vars[eval_func_param_names.index('instruction')] = \
                eval_vars[eval_func_param_names.index('instruction_nochat')] = instruction
            eval_vars[eval_func_param_names.index('iinput')] = \
                eval_vars[eval_func_param_names.index('iinput_nochat')] = ''  # no input yet
            eval_vars[eval_func_param_names.index('context')] = ''  # no context yet

            # grab other parameters, like langchain_mode
            for k in eval_func_param_names:
                if k in locals():
                    eval_vars[eval_func_param_names.index(k)] = locals()[k]

            gener = fun(*tuple(eval_vars))
            outr = ''
            res_old = ''
            for gen_output in gener:
                res = gen_output['response']
                extra = gen_output['sources']
                if base_model not in non_hf_types:
                    if not stream_output:
                        print(res)
                    else:
                        # then stream output for gradio that has full output each generation, so need here to show only new chars
                        diff = res[len(res_old):]
                        print(diff, end='', flush=True)
                        res_old = res
                    outr = res  # don't accumulate
                else:
                    outr += res  # just is one thing
                    if base_model in ['llama']:
                        # full thing, no streaming until fixed
                        print(outr, flush=True)
                    elif extra:
                        # show sources at end after model itself had streamed to std rest of response
                        print(extra, flush=True)
            all_generations.append(outr + '\n')
            if not cli_loop:
                break
    return all_generations

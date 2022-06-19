# -*- coding: utf-8 -*-

# This is an Alexa Skill where GPT-3 talks to you instead of Alexa.
# The skill serves as a simple sample on how to get responses for
# arbitrary speech and receive coherent speech in return.
import random
import logging
import os
import boto3
import requests

from ask_sdk_core.skill_builder import CustomSkillBuilder
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_core.handler_input import HandlerInput

from ask_sdk_model import Response
from ask_sdk_dynamodb.adapter import DynamoDbAdapter

SKILL_NAME = 'Arbitrary Speech'
INTRO_SPEECH = 'Welcome to the GPT-3 Interface.'
ddb_region = os.environ.get('DYNAMODB_PERSISTENCE_REGION')
ddb_table_name = os.environ.get('DYNAMODB_PERSISTENCE_TABLE_NAME')
ddb_resource = boto3.resource('dynamodb', region_name=ddb_region)
dynamodb_adapter = DynamoDbAdapter(table_name=ddb_table_name, create_table=False, dynamodb_resource=ddb_resource)
sb = CustomSkillBuilder(persistence_adapter=dynamodb_adapter)

### User settings
STARTING_CONTEXT = ['The following is a conversation with an AI assistant through a voice interface. The assistant is helpful, creative, clever, and very friendly.']
openai_organization = 'YOUR_ORG_HERE'
openai_apikey = 'YOUR_KEY_HERE'
openai_url = 'https://api.openai.com/v1/engines/text-davinci-002/completions'
openai_voice = "Matthew"
openai_temperature = 0.9
openai_max_tokens = 150
max_context_size = 50

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

@sb.request_handler(can_handle_func=is_request_type("LaunchRequest"))
def launch_request_handler(handler_input):
    """Handler for Skill Launch.

    Get the persistence attributes, to carry on a conversation you got distracted from.
    """
    # type: (HandlerInput) -> Response
    logger.info('Starting skill.')
    attr = handler_input.attributes_manager.persistent_attributes
    
    #clean slate
    if not attr:
        attr['user_response'] = 'Nothing'
        attr['gpt_response'] = 'Nothing'
        attr['gpt_context'] = STARTING_CONTEXT

    handler_input.attributes_manager.session_attributes = attr

    speech_text = (
        '<voice name="' + openai_voice + '">Welcome to the GPT-3 Interface.</voice>')
    reprompt = "Try saying 'body' followed by anything."

    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=is_intent_name("AMAZON.HelpIntent"))
def help_intent_handler(handler_input):
    """Handler for Help Intent.
    
    Let the user know about the different functions inside the skill."""
    # type: (HandlerInput) -> Response
    speech_text = (
        "Say, 'body', to create the body of a message to send to GPT-3. Other commands include 'clear context' and 'say again?'")
    reprompt = "Body. Clear context. Say again?"

    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(
    can_handle_func=lambda input:
        is_intent_name("AMAZON.CancelIntent")(input) or
        is_intent_name("AMAZON.StopIntent")(input))
def cancel_and_stop_intent_handler(handler_input):
    """Single handler for Cancel and Stop Intent."""
    # type: (HandlerInput) -> Response
    speech_text = 'Connection, closed!'

    handler_input.response_builder.speak(
        speech_text).set_should_end_session(True)
    return handler_input.response_builder.response

@sb.request_handler(can_handle_func=is_request_type("SessionEndedRequest"))
def session_ended_request_handler(handler_input):
    """Handler for Session End."""
    # type: (HandlerInput) -> Response
    logger.info(
        "Session ended with reason: {}".format(
            handler_input.request_envelope.request.reason))
    return handler_input.response_builder.response


# GPT-3 Interface -------------------------------------------------------------------------
# Uses API calls to send userCommand over to GPT-3
# Then speaks the response GPT-3 sent back
@sb.request_handler(can_handle_func=lambda input:
                    is_intent_name("UserCommandIntent")(input))
def user_command_handler(handler_input):
    session_attr = handler_input.attributes_manager.session_attributes
    user_input = handler_input.request_envelope.request.intent.slots["UserCommand"].value
    
    # gather user response
    session_attr['user_response'] = "{}".format(user_input)
    session_attr['gpt_context'].append('Human: ' + session_attr['user_response'])
    #speech_text = "Sent: {}.".format(user_input)
    reprompt = "Reprompt for User Command."
    
    # trim context so we don't pay too much
    if len(session_attr['gpt_context']) > max_context_size:
        context = session_attr['gpt_context']
        context.pop(1)
        context.pop(1)
        session_attr['gpt_context'] = context
    
    # send user response to GPT-3
    params = {'prompt': ('\n'.join(session_attr['gpt_context']) + '\nAI: '), 'temperature': openai_temperature, 'max_tokens': openai_max_tokens, 'stop': '\nHuman:'}
    response = requests.post(openai_url, auth=('', openai_apikey), json=params)
    
    # clean up GPT-3 response
    session_attr['gpt_response'] = response.json()['choices'][0]['text'].strip()
    session_attr['gpt_context'].append('AI: ' + session_attr['gpt_response'])
    speech_text = session_attr['gpt_response']
    
    # save context
    handler_input.attributes_manager.session_attributes = session_attr
    handler_input.attributes_manager.persistent_attributes = handler_input.attributes_manager.session_attributes
    handler_input.attributes_manager.save_persistent_attributes()
    
    # speak output
    handler_input.response_builder.speak('<voice name="' + openai_voice + '">' + speech_text + '</voice>').ask(reprompt)
    return handler_input.response_builder.response

@sb.request_handler(can_handle_func=lambda input:
                    is_intent_name("ClearContextIntent")(input))
def clear_context_handler(handler_input):
    session_attr = handler_input.attributes_manager.session_attributes
    
    session_attr['user_response'] = 'Nothing'
    session_attr['gpt_response'] = 'Nothing'
    session_attr['gpt_context'] = STARTING_CONTEXT
    speech_text = INTRO_SPEECH
    reprompt = "Say 'body' to start your message to GPT-3."
    
    handler_input.attributes_manager.session_attributes = session_attr
    handler_input.attributes_manager.persistent_attributes = handler_input.attributes_manager.session_attributes
    handler_input.attributes_manager.save_persistent_attributes()
    
    # inform user of success
    handler_input.response_builder.speak('Context cleared... <voice name="' + openai_voice + '">' + speech_text + '</voice>').ask(reprompt)
    return handler_input.response_builder.response

@sb.request_handler(can_handle_func=lambda input:
                    is_intent_name("SayAgainIntent")(input))
def say_again_intent_handler(handler_input):
    """Handler for repeating the last thing that was said."""
    # type: (HandlerInput) -> Response
    session_attr = handler_input.attributes_manager.session_attributes
    
    speech_text = '<voice name="' + openai_voice + '">' + session_attr['gpt_response'] + '</voice>'
    reprompt = 'You had said... {}'.format(session_attr['user_response'])

    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response

@sb.request_handler(can_handle_func=lambda input:
                    is_intent_name("AMAZON.FallbackIntent")(input))
def fallback_handler(handler_input):
    """AMAZON.FallbackIntent is only available in en-US locale.
    This handler will not be triggered except in that locale,
    so it is safe to deploy on any locale.
    """
    # type: (HandlerInput) -> Response
    session_attr = handler_input.attributes_manager.session_attributes

    speech_text = (
        "Fallback Intent. Say 'help' for help."
        )
    reprompt = "Say 'help' for help."
    
    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input: True)
def unhandled_intent_handler(handler_input):
    """Handler for all other unhandled requests."""
    # type: (HandlerInput) -> Response
    speech = "Unhandled intent."
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response


@sb.exception_handler(can_handle_func=lambda i, e: True)
def all_exception_handler(handler_input, exception):
    """Catch all exception handler, log exception and
    respond with custom message.
    """
    # type: (HandlerInput, Exception) -> Response
    logger.error(exception, exc_info=True)
    speech = "Sorry, there was an exception."
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response


@sb.global_response_interceptor()
def log_response(handler_input, response):
    """Response logger."""
    # type: (HandlerInput, Response) -> None
    logger.info("Response: {}".format(response))


lambda_handler = sb.lambda_handler()

def initialization_handlers(dp):
    from .client.client_main import register_handlers_client_main
    from .client.client_profile import register_handlers_client_profile
    from .client.client_support import register_handlers_client_support

    from .admin.admin_menu import register_handlers_admin_main
    from bot.handlers.admin.admin_alert import register_handlers_admin_alert
    from .admin.admin_bot_info import register_handlers_admin_bot_info
    from .admin.admin_admins import register_handlers_admin_admins
    from .admin.admin_notifications import register_handlers_admin_notifications
    from .admin.admin_topics import register_handlers_admin_topics
    from .admin.admin_support import register_admin_handlers_support

    from .other.error_handler import register_error_handlers
    from .other.not_handled import register_not_handled
    from .client.client_group import register_handlers_client_group
    from .other.files_fsm import register_handlers_files_fsm

    register_error_handlers(dp)

    register_handlers_client_group(dp)
    register_handlers_client_main(dp)
    register_handlers_client_profile(dp)
    register_handlers_client_support(dp)

    register_handlers_admin_main(dp)
    register_handlers_admin_alert(dp)
    register_handlers_admin_bot_info(dp)
    register_handlers_admin_admins(dp)
    register_handlers_admin_notifications(dp)
    register_handlers_admin_topics(dp)
    register_admin_handlers_support(dp)

    register_handlers_files_fsm(dp)
    register_not_handled(dp)

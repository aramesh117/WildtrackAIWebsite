import os


class AzureAuthentication:
    """
    Azure authentication related configurations
    """

    #b2c_tenant = "wildtrackcontributors"
    b2c_tenant = "wildtrackai"
    #signupsignin_user_flow = "B2C_1_simple_signup_signin"
    signin_user_flow = "B2C_1_wildtrackailogin"
    signup_user_flow = "B2C_1_wildtrackaisignup"
    #editprofile_user_flow = "B2C_1_simple_profile_editing"
    editprofile_user_flow = "B2C_1_wildtrackaiprofile"
    #resetpassword_user_flow = "B2C_1_simple_password_reset"
    resetpassword_user_flow = "B2C_1_wildtrackaipasswordreset"
    authority_template = "https://{tenant}.b2clogin.com/{tenant}.onmicrosoft.com/{user_flow}"

    #CLIENT_ID = "1e20a74c-ad67-47c7-a613-6c2a3b978277"  # Application (client) ID of app registration (Aadi)
    CLIENT_ID = "fed8383c-64b9-4e7d-abf3-aed4b76551b4"  # Application (client) ID of app registration (Joonathan)
    #CLIENT_SECRET = "3Ra_40_0-q2Jrn9I.c3eJ6z4POQ2YAdD_v"  # Placeholder - for use ONLY during testing (Aadi)
    CLIENT_SECRET = "mj5Y-zY0TmmijU9hcxLZRO37-_HS-43_PU"  # For use during testing (JOnathan)
    # In a production app, we recommend you use a more secure method of storing your secret,
    # like Azure Key Vault. Or, use an environment variable as described in Flask's documentation:
    # https://flask.palletsprojects.com/en/1.1.x/config/#configuring-from-environment-variables
    # CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    # if not CLIENT_SECRET:
    #     raise ValueError("Need to define CLIENT_SECRET environment variable")

    AUTHORITY = authority_template.format(
        tenant=b2c_tenant, user_flow=signin_user_flow)
    B2C_SIGNUP_AUTHORITY = authority_template.format(
        tenant=b2c_tenant, user_flow=signup_user_flow)
    B2C_PROFILE_AUTHORITY = authority_template.format(
        tenant=b2c_tenant, user_flow=editprofile_user_flow)
    B2C_RESET_PASSWORD_AUTHORITY = authority_template.format(
        tenant=b2c_tenant, user_flow=resetpassword_user_flow)

    REDIRECT_PATH = "/getAToken"  # Used for forming an absolute URL to your redirect URI.
    # The absolute URL must match the redirect URI you set
    # in the app's registration in the Azure portal.

    # This is the API resource endpoint
    ENDPOINT = ''  # Application ID URI of app registration in Azure portal

    # These are the scopes you've exposed in the web API app registration in the Azure portal
    SCOPE = []  # Example with two exposed scopes: ["demo.read", "demo.write"]

    SESSION_TYPE = "filesystem"  # Specifies the token cache should be stored in server-side session

    

module com
{
    module hst
    {
        module proxy
        {
            module model
            {
                sequence<byte> byteArray;

                ["java:getset"]
                struct Response
                {
                    int resultCode;

                    byteArray result;
                };

                ["java:getset"]
                struct Request
                {
                    string className;

                    string method;
                    
                    string version;

                    byteArray params;
                };
            };
        };
    };
};
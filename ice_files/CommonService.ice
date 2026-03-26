#include "CommonModel.ice"

module com
{
	module hst
	{
		module proxy
		{
			module service
			{
				module common
				{
					["ami", "amd"] interface CommonService
					{
						int invoke(model::Request request, out model::Response response);
					};
				};
			};

		};
	};
};